'use strict';
let sessionId = null;
const el = (id) => document.getElementById(id);
const error = el('error');

function markActivated(button) {
  if (!button) return;
  document.querySelectorAll('button.is-last-activated').forEach((previous) => {
    previous.classList.remove('is-last-activated');
  });
  button.classList.add('is-last-activated');
}

function findingButtonLabel(finding) {
  const subjects = {
    maximum: 'peak claim',
    minimum: 'minimum claim',
    trend: 'trend claim',
    value: 'reported number',
    unit: 'stated unit',
    claim: 'claim',
  };
  const subject = subjects[finding.kind] || 'claim';
  const about = finding.series ? ` for ${finding.series}` : '';
  let action;
  switch (finding.status) {
    case 'contradicted':
      action = `See why the ${subject}${about} conflicts with the data.`;
      break;
    case 'verified':
      action = `See how the ${subject}${about} matches the data.`;
      break;
    case 'unverifiable':
      action = `See why the data cannot verify this ${subject}${about}.`;
      break;
    case 'missing':
      action = finding.series
        ? `See why ${finding.series} is listed as missing from the description.`
        : 'See which data series the description leaves out.';
      break;
    default:
      action = 'Explore this finding and its source evidence.';
  }
  return `${finding.id}. ${action}`;
}

// Delegation also covers finding buttons created after verification.
document.addEventListener('click', (event) => {
  markActivated(event.target.closest('button'));
});

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
  markActivated(event.submitter || el('verify-form').querySelector('button[type="submit"]'));
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
      button.textContent = findingButtonLabel(finding);
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
  markActivated(event.submitter || el('ask-form').querySelector('button[type="submit"]'));
  ask(el('question').value);
});
el('summary-button').addEventListener('click', () => ask('summary'));
el('source-button').addEventListener('click', () => ask('show evidence'));
el('correction-button').addEventListener('click', () => ask('corrected description'));
