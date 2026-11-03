const input = document.querySelector('#commandInput');
const submitBtn = document.querySelector('#submitBtn');
const voiceBtn = document.querySelector('#voiceBtn');
const resultBox = document.querySelector('#resultBox');
const itemsList = document.querySelector('#itemsList');
const itemTemplate = document.querySelector('#itemTemplate');
const refreshBtn = document.querySelector('#refreshBtn');
const searchBtn = document.querySelector('#searchBtn');
const searchInput = document.querySelector('#searchInput');
const notifyBtn = document.querySelector('#notifyBtn');
const speechStatus = document.querySelector('#speechStatus');
const reminderPanel = document.querySelector('#reminderPanel');

const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai';

function showResult(data) {
  resultBox.textContent = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function formatDate(value) {
  if (!value) return '';
  return new Date(value).toLocaleString('zh-CN');
}

async function loadItems(query = '') {
  const params = new URLSearchParams({ type: 'any', status: 'active' });
  if (query) params.set('q', query);
  const items = await requestJson(`/api/items?${params}`);
  itemsList.innerHTML = '';
  if (!items.length) {
    itemsList.innerHTML = '<p class="empty">暂无记录</p>';
    return;
  }
  for (const item of items) {
    const node = itemTemplate.content.cloneNode(true);
    node.querySelector('.badge').textContent = item.item_type === 'reminder' ? '提醒' : '记事';
    node.querySelector('h3').textContent = item.title || item.content.slice(0, 24);
    node.querySelector('p').textContent = item.content;
    node.querySelector('small').textContent = item.item_type === 'reminder'
      ? `下次提醒：${formatDate(item.next_run_at) || '未设置'}`
      : `创建于：${formatDate(item.created_at)}`;
    node.querySelector('.danger').addEventListener('click', async () => {
      if (!confirm('确认物理删除这条记录？删除后不可恢复。')) return;
      await requestJson(`/api/items/${item.id}`, { method: 'DELETE' });
      await loadItems(searchInput.value.trim());
    });
    itemsList.appendChild(node);
  }
}

submitBtn.addEventListener('click', async () => {
  const text = input.value.trim();
  if (!text) return;
  submitBtn.disabled = true;
  showResult('解析中...');
  try {
    const data = await requestJson('/api/commands', {
      method: 'POST',
      body: JSON.stringify({ text, timezone, client_now: new Date().toISOString(), auto_execute: true }),
    });
    showResult(data);
    input.value = '';
    await loadItems();
  } catch (error) {
    showResult(`出错：${error.message}`);
  } finally {
    submitBtn.disabled = false;
  }
});

input.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') submitBtn.click();
});
refreshBtn.addEventListener('click', () => loadItems());
searchBtn.addEventListener('click', () => loadItems(searchInput.value.trim()));

notifyBtn.addEventListener('click', async () => {
  if (!('Notification' in window)) {
    alert('当前浏览器不支持系统通知。');
    return;
  }
  const permission = await Notification.requestPermission();
  notifyBtn.textContent = permission === 'granted' ? '系统通知已开启' : '系统通知未授权';
});

function showReminder(event) {
  reminderPanel.classList.remove('empty');
  const card = document.createElement('div');
  card.className = 'reminder-card';
  card.innerHTML = `<strong>${event.message}</strong><br><small>${formatDate(event.triggered_at)}</small><br>`;
  const ack = document.createElement('button');
  ack.className = 'secondary';
  ack.textContent = '知道了';
  ack.addEventListener('click', async () => {
    if (event.event_id) await requestJson(`/api/reminder-events/${event.event_id}/ack`, { method: 'POST' });
    card.remove();
  });
  card.appendChild(ack);
  reminderPanel.prepend(card);

  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification('AI记事本提醒', { body: event.message });
  }
}

function connectReminderStream() {
  const source = new EventSource('/api/events/reminders');
  source.addEventListener('reminder_due', (message) => {
    showReminder(JSON.parse(message.data));
    loadItems();
  });
  source.onerror = () => {
    console.warn('提醒连接断开，浏览器会自动重连');
  };
}

function setupSpeech() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    speechStatus.textContent = '当前浏览器不支持语音识别，请使用文字输入。';
    voiceBtn.disabled = true;
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = 'zh-CN';
  recognition.interimResults = true;
  recognition.continuous = true;
  let finalText = '';

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const transcript = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += transcript;
      else interim += transcript;
    }
    input.value = `${finalText}${interim}`.trim();
  };
  recognition.onerror = (event) => {
    speechStatus.textContent = `语音识别失败：${event.error}`;
  };

  const start = () => {
    finalText = input.value.trim();
    voiceBtn.classList.add('recording');
    voiceBtn.textContent = '松开结束';
    speechStatus.textContent = '正在听...';
    recognition.start();
  };
  const stop = () => {
    voiceBtn.classList.remove('recording');
    voiceBtn.textContent = '按住说话';
    speechStatus.textContent = '语音输入已结束，可编辑后提交。';
    recognition.stop();
  };
  voiceBtn.addEventListener('pointerdown', start);
  voiceBtn.addEventListener('pointerup', stop);
  voiceBtn.addEventListener('pointercancel', stop);
  voiceBtn.addEventListener('pointerleave', () => {
    if (voiceBtn.classList.contains('recording')) stop();
  });
}

setupSpeech();
connectReminderStream();
loadItems();
