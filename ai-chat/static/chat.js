(() => {
  const form = document.getElementById("form");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const messages = document.getElementById("messages");
  const backendTag = document.getElementById("backend-tag");
  const history = [];

  // Тонкая безопасная рендер-обёртка: экранируем HTML, оставляем `code`,
  // переводим ```...``` в <pre><code> и одиночные \n в <br>.
  function renderMarkdownSafe(text) {
    const escape = (s) =>
      s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    let out = "";
    const parts = text.split(/```/);
    for (let i = 0; i < parts.length; i++) {
      if (i % 2 === 1) {
        out += `<pre><code>${escape(parts[i])}</code></pre>`;
      } else {
        let chunk = escape(parts[i]);
        chunk = chunk.replace(/`([^`]+)`/g, "<code>$1</code>");
        chunk = chunk.replace(/\n/g, "<br>");
        out += chunk;
      }
    }
    return out;
  }

  function addMessage(role, text, tools) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = renderMarkdownSafe(text);
    if (tools && tools.length) {
      const tr = document.createElement("div");
      tr.className = "tool-trace";
      tr.textContent = "tools: " + tools.join(", ");
      bubble.appendChild(tr);
    }
    wrap.appendChild(bubble);
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
    return wrap;
  }

  function setBusy(busy) {
    sendBtn.disabled = busy;
    input.disabled = busy;
  }

  async function send(text) {
    addMessage("user", text);
    history.push({ role: "user", text });

    const placeholder = addMessage("model", "");
    placeholder.querySelector(".bubble").innerHTML =
      '<span class="typing">думаю…</span>';

    setBusy(true);
    try {
      const r = await fetch("./chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history }),
      });
      if (!r.ok) {
        throw new Error(`HTTP ${r.status}`);
      }
      const data = await r.json();
      placeholder.remove();
      addMessage("model", data.reply || "(пустой ответ)", data.used_tools);
      history.push({ role: "model", text: data.reply || "" });
      if (data.backend && backendTag) {
        backendTag.textContent =
          data.backend === "mcp" ? "MCP · OpenMetadata" : "REST · OpenMetadata";
      }
    } catch (e) {
      placeholder.querySelector(".bubble").innerHTML =
        renderMarkdownSafe(`Ошибка: ${e.message}`);
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    input.style.height = "auto";
    send(text);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  });

  // Подтянуть статус backend из /health
  fetch("./health")
    .then((r) => r.json())
    .then((h) => {
      if (!backendTag) return;
      backendTag.textContent = h.mcp_enabled
        ? "MCP · OpenMetadata"
        : "REST · OpenMetadata";
    })
    .catch(() => {
      if (backendTag) backendTag.textContent = "offline";
    });

  input.focus();
})();
