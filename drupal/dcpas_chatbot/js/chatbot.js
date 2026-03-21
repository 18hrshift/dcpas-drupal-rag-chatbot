/**
 * @file
 * DCPAS Chatbot frontend — handles user input, API calls, and response rendering.
 *
 * No jQuery dependency. Uses vanilla JS fetch() with the CSRF token injected
 * via drupalSettings by the block build() method.
 *
 * Security: all user input is rendered as textContent (never innerHTML),
 * and API answer text is also inserted as textContent to prevent XSS.
 */
(function (Drupal, drupalSettings, once) {
  'use strict';

  /**
   * Attach the chatbot behavior once per page load.
   */
  Drupal.behaviors.dcpasChatbot = {
    attach(context) {
      const widgets = once('dcpas-chatbot-init', '#dcpas-chatbot', context);
      if (!widgets.length) return;
      initChatbot(widgets[0]);
    },
  };

  function initChatbot(widget) {
    const form      = widget.querySelector('#dcpas-chatbot-form');
    const input     = widget.querySelector('#dcpas-chatbot-input');
    const messages  = widget.querySelector('#dcpas-chatbot-messages');
    const charCount = widget.querySelector('#dcpas-chatbot-charcount');
    const settings  = drupalSettings.dcpasChatbot || {};

    // --- Character counter ---
    input.addEventListener('input', () => {
      const remaining = 500 - input.value.length;
      charCount.textContent = remaining < 100 ? `${remaining} characters remaining` : '';
    });

    // --- Submit on Enter (but Shift+Enter = new line) ---
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      }
    });

    // --- Form submit ---
    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const question = input.value.trim();
      if (!question) return;

      appendMessage('user', question);
      input.value = '';
      charCount.textContent = '';

      const loadingEl = appendLoading();
      setFormEnabled(false, form);

      try {
        const data = await sendQuestion(question, settings);
        loadingEl.remove();

        if (data.error) {
          appendMessage('error', data.error);
        } else {
          appendMessage('assistant', data.answer, data.citations || []);
        }
      } catch (err) {
        loadingEl.remove();
        appendMessage('error', 'A network error occurred. Please try again.');
      } finally {
        setFormEnabled(true, form);
        input.focus();
        scrollToBottom(messages);
      }
    });

    // --- Helpers ---

    function appendMessage(role, text, citations) {
      const el = document.createElement('div');
      el.className = `dcpas-chatbot__message dcpas-chatbot__message--${role}`;

      const p = document.createElement('p');
      // Use textContent — NEVER innerHTML — to prevent XSS
      p.textContent = text;
      el.appendChild(p);

      if (citations && citations.length > 0) {
        const sourcesEl = document.createElement('div');
        sourcesEl.className = 'dcpas-chatbot__citations';

        const label = document.createElement('p');
        label.className = 'dcpas-chatbot__citations-label';
        label.textContent = 'Sources:';
        sourcesEl.appendChild(label);

        const ul = document.createElement('ul');
        citations.forEach((cite) => {
          // Client-side guard: only allow https:// URLs even though the server
          // validates scheme at index time. Defence-in-depth against any
          // javascript: or data: URI that might slip through.
          if (!cite.url || !cite.url.startsWith('https://')) return;

          const li = document.createElement('li');
          const a  = document.createElement('a');
          a.href   = cite.url;
          a.target = '_blank';
          a.rel    = 'noopener noreferrer';
          a.textContent = cite.title; // textContent, not innerHTML
          li.appendChild(a);
          ul.appendChild(li);
        });
        sourcesEl.appendChild(ul);
        el.appendChild(sourcesEl);
      }

      messages.appendChild(el);
      scrollToBottom(messages);
      return el;
    }

    function appendLoading() {
      const el = document.createElement('div');
      el.className = 'dcpas-chatbot__message dcpas-chatbot__message--loading';
      el.setAttribute('aria-label', 'Thinking…');
      // Build dots with createElement — never innerHTML — to avoid XSS vectors.
      for (let i = 0; i < 3; i++) {
        const dot = document.createElement('span');
        dot.className = 'dcpas-chatbot__dot';
        el.appendChild(dot);
      }
      messages.appendChild(el);
      scrollToBottom(messages);
      return el;
    }

    function scrollToBottom(el) {
      el.scrollTop = el.scrollHeight;
    }

    function setFormEnabled(enabled, f) {
      f.querySelector('button[type=submit]').disabled = !enabled;
      f.querySelector('textarea').disabled = !enabled;
    }

    async function sendQuestion(question, cfg) {
      const response = await fetch(cfg.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: question,
          token: cfg.csrfToken,
        }),
        credentials: 'same-origin',
      });

      if (!response.ok && response.status !== 429) {
        throw new Error(`HTTP ${response.status}`);
      }

      return response.json();
    }
  }

}(Drupal, drupalSettings, once));
