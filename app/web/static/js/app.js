// ClipStream AI - Frontend Controller

let currentContentType = 'gaming';
let currentLayout = 'gaming_split';
let currentSubtitle = 'mrbeast';
let currentFontSize = 85;
let currentFocusPosition = 'auto';
let currentFacecamPosition = 'auto';
let activityChart = null;
let discoveredClips = [];
let activeClip = null;
let livePollInterval = null;
// Store the original source video path so export always cuts from the full video
let sourceVideoPath = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  fetchSystemStatus();
  fetchSavedKeys();
});

// Tab Navigation
function switchTab(tabName) {
  const tabs = ['studio', 'live', 'settings'];
  tabs.forEach(t => {
    const el = document.getElementById(`tab-${t}`);
    const btn = document.getElementById(`tab-btn-${t}`);
    if (t === tabName) {
      el.classList.remove('hidden');
      btn.classList.add('bg-indigo-600', 'text-white');
      btn.classList.remove('text-slate-400');
    } else {
      el.classList.add('hidden');
      btn.classList.remove('bg-indigo-600', 'text-white');
      btn.classList.add('text-slate-400');
    }
  });
  lucide.createIcons();
}

function setContentType(type) {
  currentContentType = type;
  const btnGaming = document.getElementById('type-gaming');
  const btnPodcast = document.getElementById('type-podcast');

  if (type === 'gaming') {
    btnGaming.className = 'px-3.5 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 text-white flex items-center space-x-1.5';
    btnPodcast.className = 'px-3.5 py-1.5 text-xs font-medium rounded-lg text-slate-400 hover:text-white flex items-center space-x-1.5 transition';
    selectLayout('gaming_split');
  } else {
    btnPodcast.className = 'px-3.5 py-1.5 text-xs font-medium rounded-lg bg-indigo-600 text-white flex items-center space-x-1.5';
    btnGaming.className = 'px-3.5 py-1.5 text-xs font-medium rounded-lg text-slate-400 hover:text-white flex items-center space-x-1.5 transition';
    selectLayout('podcast_blur');
  }
}

// System Status & Keys
async function fetchSystemStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    const geminiText = document.getElementById('gemini-status-text');
    const groqText = document.getElementById('groq-status-text');

    if (data.gemini_configured) {
      geminiText.innerText = 'Gemini Ready';
      document.getElementById('badge-gemini').classList.replace('bg-slate-800', 'bg-indigo-500/10');
      document.getElementById('badge-gemini').classList.replace('text-slate-300', 'text-indigo-400');
    } else {
      geminiText.innerText = 'Gemini Key Needed';
    }

    if (data.groq_configured) {
      groqText.innerText = 'Groq Ready';
      document.getElementById('badge-groq').classList.replace('bg-slate-800', 'bg-amber-500/10');
      document.getElementById('badge-groq').classList.replace('text-slate-300', 'text-amber-400');
    } else {
      groqText.innerText = 'Groq Key Needed';
    }
  } catch (err) {
    console.error('Status check error:', err);
  }
}

async function fetchSavedKeys() {
  try {
    const res = await fetch('/api/settings/keys');
    const data = await res.json();
    if (data.gemini_is_set) {
      document.getElementById('input-gemini-key').placeholder = `Configured: ${data.gemini_api_key}`;
    }
    if (data.groq_is_set) {
      document.getElementById('input-groq-key').placeholder = `Configured: ${data.groq_api_key}`;
    }
  } catch (err) {
    console.error('Error fetching keys:', err);
  }
}

async function saveApiKeys() {
  const gemini = document.getElementById('input-gemini-key').value.trim();
  const groq = document.getElementById('input-groq-key').value.trim();
  const msgEl = document.getElementById('settings-save-msg');

  try {
    const res = await fetch('/api/settings/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gemini_api_key: gemini, groq_api_key: groq })
    });
    const data = await res.json();
    msgEl.innerText = 'API keys saved successfully to .env!';
    msgEl.classList.remove('hidden');
    fetchSystemStatus();
    setTimeout(() => msgEl.classList.add('hidden'), 4000);
  } catch (err) {
    msgEl.innerText = `Save error: ${err.message}`;
    msgEl.classList.remove('hidden');
  }
}

async function testKey(provider) {
  const keyInput = document.getElementById(provider === 'gemini' ? 'input-gemini-key' : 'input-groq-key');
  const resultEl = document.getElementById(`${provider}-test-result`);
  const keyVal = keyInput.value.trim();

  if (!keyVal) {
    resultEl.innerText = 'Please paste a key first to test.';
    resultEl.className = 'text-xs text-rose-400';
    resultEl.classList.remove('hidden');
    return;
  }

  resultEl.innerText = 'Testing connection...';
  resultEl.className = 'text-xs text-indigo-400';
  resultEl.classList.remove('hidden');

  try {
    const res = await fetch('/api/settings/test-key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, api_key: keyVal })
    });
    const data = await res.json();
    if (data.status === 'success') {
      resultEl.innerText = `✓ ${data.message}`;
      resultEl.className = 'text-xs text-emerald-400 font-semibold';
    } else {
      resultEl.innerText = `✗ ${data.message}`;
      resultEl.className = 'text-xs text-rose-400';
    }
  } catch (err) {
    resultEl.innerText = `Connection failed: ${err.message}`;
    resultEl.className = 'text-xs text-rose-400';
  }
}

// Video Processing
async function processVideo() {
  const url = document.getElementById('video-url-input').value.trim();
  if (!url) {
    alert('Please enter a YouTube video URL or local file path.');
    return;
  }

  const loader = document.getElementById('processing-loader');
  const btn = document.getElementById('btn-process-video');
  const statusMsg = document.getElementById('processing-status-msg');

  loader.classList.remove('hidden');
  btn.disabled = true;
  btn.classList.add('opacity-50');

  try {
    statusMsg.innerText = 'Analyzing stream chat spikes & audio waveforms...';
    const res = await fetch('/api/process/vod', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: url,
        content_type: currentContentType,
        min_clip_duration: 25,
        max_clip_duration: 60
      })
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Processing failed');
    }

    const data = await res.json();
    discoveredClips = data.clips || [];

    // ✅ Store the original source path for exports
    sourceVideoPath = data.video_info.source_path;

    // Render timeline
    if (data.chat_timeline.length > 0 || data.audio_timeline.length > 0) {
      renderActivityTimeline(data.chat_timeline, data.audio_timeline);
      document.getElementById('timeline-card').classList.remove('hidden');
      document.getElementById('video-title-display').innerText = data.video_info.title;
    }

    // Render clips list
    renderClipsList(discoveredClips);
    document.getElementById('results-section').classList.remove('hidden');

    // Automatically select the highest scoring clip
    if (discoveredClips.length > 0) {
      selectClip(discoveredClips[0]);
    }

  } catch (err) {
    alert(`Processing failed: ${err.message}`);
  } finally {
    loader.classList.add('hidden');
    btn.disabled = false;
    btn.classList.remove('opacity-50');
  }
}

function renderActivityTimeline(chatData, audioData) {
  const ctx = document.getElementById('activityChart').getContext('2d');
  if (activityChart) {
    activityChart.destroy();
  }

  const labels = chatData.length > 0 ? chatData.map(d => `${Math.floor(d.time / 60)}:${Math.floor(d.time % 60).toString().padStart(2, '0')}`) : audioData.map(d => `${Math.floor(d.time / 60)}:${Math.floor(d.time % 60).toString().padStart(2, '0')}`);
  const velocities = chatData.map(d => d.velocity);
  const audioValues = audioData.map(d => d.db);

  activityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Chat Message Velocity (msgs/sec)',
          data: velocities,
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99, 102, 241, 0.2)',
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 0
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: { color: '#64748b', maxTicksLimit: 12 },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        y: {
          ticks: { color: '#64748b' },
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        }
      },
      plugins: {
        legend: { labels: { color: '#94a3b8' } }
      }
    }
  });
}

function renderClipsList(clips) {
  const listEl = document.getElementById('clips-list');
  const countBadge = document.getElementById('clips-count-badge');
  countBadge.innerText = `${clips.length} Viral Moments`;
  listEl.innerHTML = '';

  if (clips.length === 0) {
    listEl.innerHTML = '<p class="text-xs text-slate-400">No peak moments detected.</p>';
    return;
  }

  clips.forEach((c, idx) => {
    const card = document.createElement('div');
    card.className = `p-4 rounded-xl border border-white/10 bg-black/40 hover:bg-black/60 cursor-pointer transition space-y-3 ${idx === 0 ? 'border-indigo-500/50 bg-indigo-950/20' : ''}`;
    card.onclick = () => selectClip(c, card);

    const title = c.viral_titles && c.viral_titles.length > 0 ? c.viral_titles[0] : `Moment at ${c.start_time}s`;

    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="viral-badge px-2.5 py-0.5 rounded-full text-[11px] font-extrabold text-white flex items-center gap-1">
            🔥 ${c.virality_score}/100
          </span>
          <span class="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            ⚡ ${c.hook_score}/10 Hook
          </span>
        </div>
        <span class="text-xs font-mono text-slate-400">${c.duration}s</span>
      </div>

      <div>
        <h4 class="text-xs font-bold text-white line-clamp-1">${title}</h4>
        <p class="text-[11px] text-slate-400 line-clamp-2 mt-0.5">"${c.transcript || 'Pure visual/gameplay highlight'}"</p>
      </div>

      <div class="flex items-center justify-between pt-1 border-t border-white/5 text-[10px] text-slate-400">
        <span>⏱ ${c.start_time}s — ${c.end_time}s</span>
        <span class="text-indigo-400 font-semibold uppercase">${c.tag}</span>
      </div>
    `;

    listEl.appendChild(card);
  });
}

function selectClip(clip, cardElement = null) {
  activeClip = clip;

  // Highlight selected card
  if (cardElement) {
    document.querySelectorAll('#clips-list > div').forEach(el => el.classList.remove('border-indigo-500/50', 'bg-indigo-950/20'));
    cardElement.classList.add('border-indigo-500/50', 'bg-indigo-950/20');
  }

  // Update virality badge
  document.getElementById('active-clip-badge').innerText = `Viral Score: ${clip.virality_score}/100`;

  // ✅ FIX: Preview player now reads from /api/media/clip/ (served from storage/clips/)
  const player = document.getElementById('preview-player');
  if (clip.raw_video_path) {
    const filename = clip.raw_video_path.split('\\').pop().split('/').pop();
    player.src = `/api/media/clip/${filename}`;
    player.load();
  }

  // ✅ FIX: Fine-tune sliders show ORIGINAL video timestamps (for cutting from source)
  document.getElementById('input-start-sec').value = clip.start_time;
  document.getElementById('input-end-sec').value = clip.end_time;
}

function selectLayout(layoutName) {
  currentLayout = layoutName;
  document.querySelectorAll('.layout-card').forEach(el => el.classList.remove('selected'));
  const target = document.getElementById(`layout-${layoutName}`);
  if (target) target.classList.add('selected');

  const panel = document.getElementById('focus-tuning-panel');
  const title = document.getElementById('focus-panel-title');
  const optSpeaker = document.getElementById('focus-options-speaker');
  const optFacecam = document.getElementById('focus-options-facecam');
  const sliderBox = document.getElementById('focus-slider-container');
  const displayVal = document.getElementById('focus-display-val');

  if (!panel) return;

  if (layoutName === 'gaming_split' || layoutName === 'pip') {
    panel.classList.remove('hidden');
    optSpeaker.classList.add('hidden');
    sliderBox.classList.add('hidden');
    optFacecam.classList.remove('hidden');
    title.innerText = 'Streamer Facecam Location:';
    displayVal.innerText = currentFacecamPosition.toUpperCase();
  } else if (layoutName === 'smart_face_track' || layoutName === 'center_crop') {
    panel.classList.remove('hidden');
    optFacecam.classList.add('hidden');
    optSpeaker.classList.remove('hidden');
    sliderBox.classList.remove('hidden');
    title.innerText = 'Speaker & Camera Focus Point:';
    displayVal.innerText = currentFocusPosition.toUpperCase();
  } else {
    // podcast_blur preserves full 16:9 view without cropping
    panel.classList.remove('hidden');
    optFacecam.classList.add('hidden');
    optSpeaker.classList.add('hidden');
    sliderBox.classList.add('hidden');
    title.innerText = 'Podcast Blurred Letterbox:';
    displayVal.innerText = 'Full View (Zero Cropping)';
  }
}

function setFocusPosition(pos) {
  currentFocusPosition = pos;
  document.querySelectorAll('.focus-chip').forEach(el => {
    el.classList.remove('bg-indigo-600', 'text-white', 'border-indigo-500');
    el.classList.add('bg-white/5', 'text-slate-300', 'border-white/10');
  });
  const btn = document.getElementById(`focus-btn-${pos}`);
  if (btn) {
    btn.classList.add('bg-indigo-600', 'text-white', 'border-indigo-500');
    btn.classList.remove('bg-white/5', 'text-slate-300', 'border-white/10');
  }

  const slider = document.getElementById('input-focus-slider');
  const pct = document.getElementById('focus-slider-pct');
  const displayVal = document.getElementById('focus-display-val');

  if (pos === 'left') {
    if (slider) slider.value = 0.28;
    if (pct) pct.innerText = '28%';
    if (displayVal) displayVal.innerText = 'Left Speaker (28%)';
  } else if (pos === 'center') {
    if (slider) slider.value = 0.50;
    if (pct) pct.innerText = '50%';
    if (displayVal) displayVal.innerText = 'Center (50%)';
  } else if (pos === 'right') {
    if (slider) slider.value = 0.72;
    if (pct) pct.innerText = '72%';
    if (displayVal) displayVal.innerText = 'Right Speaker (72%)';
  } else {
    if (slider) slider.value = 0.50;
    if (pct) pct.innerText = 'Auto';
    if (displayVal) displayVal.innerText = 'Auto AI Detect';
  }
}

function onFocusSliderChange(val) {
  currentFocusPosition = val;
  const pct = Math.round(parseFloat(val) * 100);
  const pctEl = document.getElementById('focus-slider-pct');
  const displayVal = document.getElementById('focus-display-val');
  if (pctEl) pctEl.innerText = `${pct}%`;
  if (displayVal) displayVal.innerText = `Custom (${pct}%)`;
  document.querySelectorAll('.focus-chip').forEach(el => {
    el.classList.remove('bg-indigo-600', 'text-white', 'border-indigo-500');
    el.classList.add('bg-white/5', 'text-slate-300', 'border-white/10');
  });
}

function setFacecamPosition(pos) {
  currentFacecamPosition = pos;
  document.querySelectorAll('.cam-chip').forEach(el => {
    el.classList.remove('bg-indigo-600', 'text-white', 'border-indigo-500');
    el.classList.add('bg-white/5', 'text-slate-300', 'border-white/10');
  });
  const btn = document.getElementById(`cam-btn-${pos}`);
  if (btn) {
    btn.classList.add('bg-indigo-600', 'text-white', 'border-indigo-500');
    btn.classList.remove('bg-white/5', 'text-slate-300', 'border-white/10');
  }
  const displayVal = document.getElementById('focus-display-val');
  if (displayVal) displayVal.innerText = pos.toUpperCase();
}

function selectSubtitle(presetName) {
  currentSubtitle = presetName;
  document.querySelectorAll('.preset-chip').forEach(el => el.classList.remove('selected'));
  const target = document.getElementById(`sub-${presetName}`);
  if (target) target.classList.add('selected');

  // Adjust font size slider default based on preset
  const presetSizes = { mrbeast: 85, hormozi: 95, cyber_neon: 85, minimal: 70 };
  if (presetSizes[presetName]) {
    const slider = document.getElementById('input-font-size');
    if (slider) {
      slider.value = presetSizes[presetName];
      updateFontSize(presetSizes[presetName]);
    }
  }
}

function updateFontSize(val) {
  currentFontSize = parseInt(val, 10);
  const label = currentFontSize >= 100 ? 'Massive Hype' : (currentFontSize >= 80 ? 'Bold Viral' : 'Standard');
  const valEl = document.getElementById('font-size-val');
  if (valEl) valEl.innerText = `${currentFontSize}px (${label})`;
}

// Export Short
async function exportSelectedShort() {
  if (!activeClip) {
    alert('Please select a viral clip to export.');
    return;
  }

  const exportBtn = document.getElementById('btn-export-short');
  const resultBox = document.getElementById('export-result-box');
  const downloadBtn = document.getElementById('btn-download-short');
  const titleDisplay = document.getElementById('export-suggested-title');

  const startSec = parseFloat(document.getElementById('input-start-sec').value) || activeClip.start_time;
  const endSec = parseFloat(document.getElementById('input-end-sec').value) || activeClip.end_time;

  // Explicitly read font size from slider DOM element to ensure 100% accuracy
  const fontSlider = document.getElementById('input-font-size');
  const chosenFontSize = fontSlider ? parseInt(fontSlider.value, 10) : (currentFontSize || 85);

  exportBtn.disabled = true;
  exportBtn.innerHTML = '<span class="animate-spin inline-block mr-2">⚙</span> Rendering 9:16 Vertical Short with Captions...';

  try {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        // Always export from the full original source video, not the preview clip.
        source_video_path: sourceVideoPath || activeClip.source_video_path || activeClip.raw_video_path,
        video_path: sourceVideoPath || activeClip.source_video_path || activeClip.raw_video_path,
        start_time: startSec,
        end_time: endSec,
        layout: currentLayout,
        subtitle_preset: currentSubtitle,
        subtitle_font_size: chosenFontSize,
        focus_position: currentFocusPosition,
        facecam_position: currentFacecamPosition,
        burn_subtitles: currentSubtitle !== 'none',
        words: activeClip.words || []
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Export failed');
    }

    const data = await res.json();
    resultBox.classList.remove('hidden');
    downloadBtn.href = data.download_url;
    downloadBtn.setAttribute('download', data.filename);

    const title = activeClip.viral_titles && activeClip.viral_titles.length > 0 ? activeClip.viral_titles[0] : 'My Viral Short';
    titleDisplay.innerText = `${title} #shorts #viral`;

  } catch (err) {
    alert(`Export error: ${err.message}`);
  } finally {
    exportBtn.disabled = false;
    exportBtn.innerHTML = '<i data-lucide="video" class="w-5 h-5"></i><span>Export Viral Short (1080x1920 60FPS)</span>';
    lucide.createIcons();
  }
}

// Live Stream Monitor
async function startLiveStream() {
  const url = document.getElementById('live-url-input').value.trim();
  if (!url) {
    alert('Please enter a live stream URL.');
    return;
  }

  try {
    const res = await fetch('/api/live/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url, quality: '720p,best' })
    });
    const data = await res.json();

    document.getElementById('btn-live-start').classList.add('hidden');
    document.getElementById('btn-live-stop').classList.remove('hidden');
    document.getElementById('live-stats-panel').classList.remove('hidden');
    document.getElementById('live-chat-box').classList.remove('hidden');

    // Start polling
    if (livePollInterval) clearInterval(livePollInterval);
    livePollInterval = setInterval(pollLiveStatus, 2000);

  } catch (err) {
    alert(`Failed to start live stream: ${err.message}`);
  }
}

async function pollLiveStatus() {
  try {
    const res = await fetch('/api/live/status');
    const data = await res.json();

    if (data.recording) {
      const sec = Math.floor(data.recording.elapsed_seconds);
      const min = Math.floor(sec / 60);
      const remSec = sec % 60;
      document.getElementById('live-duration-text').innerText = `${min.toString().padStart(2, '0')}:${remSec.toString().padStart(2, '0')}`;
    }

    document.getElementById('live-chat-count-text').innerText = `${data.chat_message_count} msgs`;
    document.getElementById('live-velocity-text').innerText = `${data.recent_velocity} msg/s`;

    const feed = document.getElementById('live-chat-messages');
    if (data.recent_messages && data.recent_messages.length > 0) {
      feed.innerHTML = data.recent_messages.map(m => `
        <div class="flex items-center space-x-2">
          <span class="text-indigo-400 font-bold">${m.author}:</span>
          <span class="text-slate-200">${m.message}</span>
        </div>
      `).join('');
      feed.scrollTop = feed.scrollHeight;
    }
  } catch (err) {
    console.error('Live poll error:', err);
  }
}

async function stopLiveStream() {
  if (livePollInterval) clearInterval(livePollInterval);

  try {
    const res = await fetch('/api/live/stop', { method: 'POST' });
    const data = await res.json();

    document.getElementById('btn-live-start').classList.remove('hidden');
    document.getElementById('btn-live-stop').classList.add('hidden');

    if (data.result && data.result.file_path) {
      alert(`Live capture saved! Duration: ${Math.round(data.result.duration)}s. Switching to Clipper Studio...`);
      switchTab('studio');
      document.getElementById('video-url-input').value = data.result.file_path;
      processVideo();
    }
  } catch (err) {
    alert(`Failed to stop live stream: ${err.message}`);
  }
}
