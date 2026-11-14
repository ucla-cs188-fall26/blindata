'use strict';
let sessionId = null;
const el = (id) => document.getElementById(id);
const error = el('error');

async function post(path, payload) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Unexpected error');
  return data;
}

function showResult(result) {
  el('answer').textContent = result.answer;
  const tableBody = el('evidence-rows');
  tableBody.replaceChildren();
  for (const row of result.evidence || []) {
    const tr = document.createElement('tr');
    for (const value of [row.row_index, row.label, row.series, row.value]) {
      const td = document.createElement('td');
      td.textContent = String(value);
      tr.appendChild(td);
    }
    tableBody.appendChild(tr);
  }
  el('evidence-section').hidden = !(result.evidence || []).length;
}

async function ask(question) {
  if (!sessionId) return;
  try {
    error.textContent = '';
    el('answer').setAttribute('aria-busy', 'true');
    const payload = await post('/api/ask', {session_id: sessionId, question});
    showResult(payload.result);
    el('agent-mode').textContent = payload.result.mode === 'llm'
      ? 'LLM tool-calling mode. Answers are model-generated; inspect the source evidence below.'
      : 'Offline evidence mode. Answers use predefined question commands.';
  } catch (e) {
    error.textContent = e.message;
  } finally {
    el('answer').removeAttribute('aria-busy');
  }
}

el('verify-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  error.textContent = '';
  sessionId = null;
  try {
    const payload = await post('/api/start', {
      format: el('format').value,
      data: el('data').value,
      description: el('description').value,
    });
    sessionId = payload.session_id;
    el('agent-mode').textContent = payload.agent_mode === 'llm'
      ? 'LLM mode enabled for follow-up questions.'
      : 'Offline rule-based mode enabled. Set OPENAI_API_KEY to enable LLM tool calling.';
    el('explorer').hidden = false;
    showResult(payload.result);
    const parent = el('finding-buttons');
    parent.replaceChildren();
    for (const finding of payload.findings) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `Inspect ${finding.id}: ${finding.status}, ${finding.kind}`;
      button.addEventListener('click', () => ask(`inspect ${finding.id}`));
      parent.appendChild(button);
    }
    el('explore-title').setAttribute('tabindex', '-1');
    el('explore-title').focus();
  } catch (e) {
    error.textContent = e.message;
  }
});

el('ask-form').addEventListener('submit', (event) => {
  event.preventDefault();
  ask(el('question').value);
});
el('summary-button').addEventListener('click', () => ask('summary'));
el('source-button').addEventListener('click', () => ask('show evidence'));
el('correction-button').addEventListener('click', () => ask('corrected description'));
