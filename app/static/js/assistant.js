(function () {
  'use strict';

  var cfg = window.__TP_ASSISTANT__;
  if (!cfg || !cfg.deviceId) {
    return;
  }

  var deviceId = cfg.deviceId;
  var stillUrl = '/api/assistant/' + encodeURIComponent(deviceId) + '/still';
  var chatUrl = '/api/assistant/' + encodeURIComponent(deviceId) + '/chat';
  var grantUrl = '/api/assistant/' + encodeURIComponent(deviceId) + '/grant';
  var stopUrl = '/api/assistant/' + encodeURIComponent(deviceId) + '/stop';
  var bootstrapUrl =
    '/api/assistant/' + encodeURIComponent(deviceId) + '/bootstrap';

  var chatAbort = null;

  function setStatus(text) {
    var el = document.getElementById('assistant-status');
    if (el && text) {
      el.textContent = text;
    }
  }

  function showFatal(message) {
    setStatus(message);
    var shell = document.getElementById('assistant-shell');
    if (shell) {
      shell.setAttribute('aria-hidden', 'true');
    }
  }

  function refreshStillImage() {
    var box =
      document.getElementById('assistant-preview-still') ||
      document.getElementById('assistant-still');
    if (!box) {
      return;
    }
    var img = box.querySelector('img');
    if (!img) {
      img = document.createElement('img');
      img.alt = 'What the Assistant sees on the remote display';
      img.className = 'assistant-still-img';
      box.appendChild(img);
    }
    img.src = stillUrl + '?t=' + String(Date.now());
  }

  function appendChatLine(role, text) {
    var log = document.getElementById('assistant-chat-log');
    if (!log) {
      return;
    }
    var line = document.createElement('div');
    line.className = 'assistant-chat-line assistant-chat-' + role;
    line.textContent = text;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  function handleChatEvent(event) {
    if (!event || !event.type) {
      return;
    }
    if (event.type === 'text' && event.text) {
      appendChatLine('assistant', event.text);
    }
    if (event.type === 'tool') {
      var label = event.name || 'tool';
      if (event.ok) {
        appendChatLine('tool', label + ' ok');
      } else {
        appendChatLine('tool', label + ': ' + (event.error || 'failed'));
      }
    }
    if (event.type === 'still') {
      refreshStillImage();
    }
    if (event.type === 'error' && event.error) {
      appendChatLine('error', event.error);
    }
    if (event.type === 'stopped') {
      appendChatLine('error', 'Stopped');
    }
  }

  function consumeChatStream(response) {
    if (!response.body || !response.body.getReader) {
      return response.text().then(function (raw) {
        raw.split('\n').forEach(function (ln) {
          if (!ln.trim()) {
            return;
          }
          try {
            handleChatEvent(JSON.parse(ln));
          } catch (_e) {
            /* ignore */
          }
        });
      });
    }
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    function pump() {
      return reader.read().then(function (chunk) {
        if (chunk.done) {
          return;
        }
        buffer += decoder.decode(chunk.value, { stream: true });
        var parts = buffer.split('\n');
        buffer = parts.pop() || '';
        parts.forEach(function (ln) {
          if (!ln.trim()) {
            return;
          }
          try {
            handleChatEvent(JSON.parse(ln));
          } catch (_e) {
            /* ignore */
          }
        });
        return pump();
      });
    }
    return pump();
  }

  function sendChatMessage(message) {
    appendChatLine('user', message);
    if (chatAbort) {
      chatAbort.abort();
    }
    chatAbort =
      typeof AbortController !== 'undefined' ? new AbortController() : null;
    var signal = chatAbort ? chatAbort.signal : undefined;
    return fetch(chatUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/x-ndjson',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message: message }),
      signal: signal,
    }).then(function (rv) {
      if (!rv.ok) {
        appendChatLine('error', 'Chat request failed');
        return;
      }
      return consumeChatStream(rv);
    });
  }

  function requestStopTurn() {
    fetch(stopUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    }).catch(function () {});
    if (chatAbort) {
      chatAbort.abort();
    }
  }

  function postGrantAllowed(allowed) {
    fetch(grantUrl, {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: true,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ allowed: allowed }),
    }).catch(function () {});
  }

  function wireGrantCheckbox() {
    var grantEl = document.getElementById('assistant-grant');
    if (!grantEl) {
      return;
    }
    grantEl.addEventListener('change', function () {
      var allowed = grantEl.checked;
      fetch(grantUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ allowed: allowed }),
      }).catch(function () {
        grantEl.checked = !allowed;
      });
    });
    window.addEventListener('pagehide', function () {
      postGrantAllowed(false);
    });
  }

  function wirePromptForm() {
    var form = document.getElementById('assistant-prompt-form');
    var input = document.getElementById('assistant-prompt');
    var submit = form ? form.querySelector('button[type="submit"]') : null;
    var stopBtn = document.getElementById('assistant-stop');
    if (!form || !input || !submit || !stopBtn) {
      return;
    }
    var inFlight = false;

    function setSending(busy) {
      inFlight = busy;
      submit.disabled = busy;
      stopBtn.disabled = !busy;
      stopBtn.hidden = !busy;
    }

    function submitPrompt() {
      var text = (input.value || '').trim();
      if (!text || inFlight) {
        return;
      }
      input.value = '';
      setSending(true);
      sendChatMessage(text)
        .catch(function (err) {
          if (err && err.name === 'AbortError') {
            appendChatLine('error', 'Stopped');
            return;
          }
          appendChatLine('error', 'Chat failed');
        })
        .finally(function () {
          chatAbort = null;
          setSending(false);
          input.focus();
        });
    }

    stopBtn.addEventListener('click', function () {
      if (!inFlight) {
        return;
      }
      requestStopTurn();
    });

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      submitPrompt();
    });

    input.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' || ev.shiftKey) {
        return;
      }
      ev.preventDefault();
      if (inFlight) {
        return;
      }
      submitPrompt();
    });
  }

  function enableRail() {
    refreshStillImage();
    wireGrantCheckbox();
    wirePromptForm();
    var input = document.getElementById('assistant-prompt');
    var submit = document.querySelector(
      '#assistant-prompt-form button[type=submit]',
    );
    if (input) {
      input.disabled = false;
    }
    if (submit) {
      submit.disabled = false;
    }
    setStatus('Ready. Live KVM: Open WebUI in another tab.');
  }

  function wireOpenWebUi() {
    fetch('/api/devices', { credentials: 'same-origin' })
      .then(function (rv) {
        return rv.json();
      })
      .then(function (data) {
        var devices = data.devices || [];
        var row = devices.find(function (d) {
          return Number(d.id) === Number(deviceId);
        });
        var link = document.getElementById('assistant-open-webui');
        if (!link || !row || !row.base_url) {
          return;
        }
        link.href = row.base_url;
        link.hidden = false;
      })
      .catch(function () {});
  }

  function startBootstrap() {
    setStatus('Capturing context still…');
    fetch(bootstrapUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
      .then(function (rv) {
        if (rv.status === 503) {
          showFatal('Assistant is not configured (set ASSISTANT_API_KEY).');
          return null;
        }
        if (rv.status === 404) {
          showFatal('Device not found on this dashboard.');
          return null;
        }
        if (!rv.ok) {
          showFatal('Could not start assistant session.');
          return null;
        }
        return rv.json();
      })
      .then(function (body) {
        if (!body || !body.ok) {
          if (body && body.error) {
            showFatal(body.error);
          }
          return;
        }
        enableRail();
      })
      .catch(function () {
        showFatal('Could not reach the dashboard.');
      });
  }

  wireOpenWebUi();
  startBootstrap();
})();