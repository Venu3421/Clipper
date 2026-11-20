import re
import time
import math
import logging
import threading
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
import pytchat

logger = logging.getLogger("clipstream.chat_analyzer")

# High-engagement hype & reaction tokens
HYPE_PATTERNS = {
    "funny": re.compile(r"\b(lol|lmao|lmfao|kekw|haha|hahaha|rofl|dead|skull|💀|😂|🤣)\b", re.IGNORECASE),
    "hype": re.compile(r"\b(w|pog|poggers|clip|clip it|clip that|holy|insane|omg|fire|sheesh|hype|goat|let's go|lets go|🔥|👏|⚡|🏆)\b", re.IGNORECASE),
    "shock": re.compile(r"\b(wtf|what|no way|noway|wait what|caught|scam|bruh|bro what|choke|whaaat|😱|🤯|👀|😳)\b", re.IGNORECASE),
}

class ChatSpikeDetector:
    def __init__(self, bucket_size_sec: int = 5, min_clip_duration: int = 25, max_clip_duration: int = 60):
        self.bucket_size = bucket_size_sec
        self.min_clip_duration = min_clip_duration
        self.max_clip_duration = max_clip_duration

    def analyze_chat_events(self, messages: List[Dict[str, Any]], video_duration: float = 0.0) -> Dict[str, Any]:
        """
        Analyze an array of chat messages with timestamps:
        messages: List of {"time_in_seconds": float, "message": str, "author": str}
        """
        if not messages:
            return {"spikes": [], "timeline": [], "message_count": 0}

        # 1. Bucket messages
        max_time = max(m.get("time_in_seconds", 0.0) for m in messages)
        if video_duration > 0:
            max_time = max(max_time, video_duration)
            
        num_buckets = math.ceil(max_time / self.bucket_size) + 1
        message_buckets = [0] * num_buckets
        hype_buckets = [0.0] * num_buckets
        sentiment_tallies = [defaultdict(int) for _ in range(num_buckets)]

        for msg in messages:
            t = msg.get("time_in_seconds", 0.0)
            if t < 0:
                continue
            bucket_idx = int(t // self.bucket_size)
            if bucket_idx < num_buckets:
                message_buckets[bucket_idx] += 1
                text = msg.get("message", "")
                
                # Check reaction types
                score = 1.0
                for category, pattern in HYPE_PATTERNS.items():
                    matches = pattern.findall(text)
                    if matches:
                        sentiment_tallies[bucket_idx][category] += len(matches)
                        score += len(matches) * 1.5
                        
                hype_buckets[bucket_idx] += score

        # 2. Compute velocity (msgs/sec) and statistics
        velocities = [count / self.bucket_size for count in message_buckets]
        total_msgs = len(messages)
        non_zero_velocities = [v for v in velocities if v > 0]
        
        mean_vel = (sum(non_zero_velocities) / len(non_zero_velocities)) if non_zero_velocities else 0.0
        variance = sum((v - mean_vel) ** 2 for v in non_zero_velocities) / len(non_zero_velocities) if non_zero_velocities else 0.0
        std_vel = math.sqrt(variance)

        # Baseline threshold: at least 1.8x std deviations above mean or min 1 msg/sec
        threshold = max(mean_vel + 1.6 * std_vel, 0.8)

        # 3. Find peak spikes
        spike_indices = [i for i, v in enumerate(velocities) if v >= threshold]

        # 4. Cluster nearby spikes into candidate clip windows
        candidate_clips = []
        if spike_indices:
            clusters: List[List[int]] = []
            current_cluster = [spike_indices[0]]

            for idx in spike_indices[1:]:
                # If within 15 seconds of previous spike, group them
                if (idx - current_cluster[-1]) * self.bucket_size <= 15:
                    current_cluster.append(idx)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [idx]
            clusters.append(current_cluster)

            for cluster in clusters:
                peak_idx = max(cluster, key=lambda i: hype_buckets[i])
                peak_time = peak_idx * self.bucket_size

                # Center the clip window around the peak
                # The peak usually happens right after the crazy event (streamer reacts -> chat explodes)
                # So we allocate ~65% of the clip BEFORE the peak and ~35% AFTER the peak!
                clip_len = min(max(self.min_clip_duration, len(cluster) * self.bucket_size + 15), self.max_clip_duration)
                
                start_sec = max(0.0, peak_time - (clip_len * 0.65))
                end_sec = start_sec + clip_len
                if video_duration > 0 and end_sec > video_duration:
                    end_sec = video_duration
                    start_sec = max(0.0, end_sec - clip_len)

                # Determine dominant sentiment
                cluster_sentiments = defaultdict(int)
                for i in cluster:
                    for cat, val in sentiment_tallies[i].items():
                        cluster_sentiments[cat] += val
                primary_tag = max(cluster_sentiments, key=cluster_sentiments.get) if cluster_sentiments else "hype"

                candidate_clips.append({
                    "start_time": round(start_sec, 2),
                    "end_time": round(end_sec, 2),
                    "duration": round(end_sec - start_sec, 2),
                    "peak_time": round(peak_time, 2),
                    "peak_velocity": round(velocities[peak_idx], 2),
                    "hype_score": round(hype_buckets[peak_idx], 1),
                    "tag": primary_tag,
                    "confidence": min(100, round((velocities[peak_idx] / max(threshold, 0.1)) * 50, 1))
                })

        # Build timeline for UI chart
        timeline = []
        for i in range(num_buckets):
            timeline.append({
                "time": i * self.bucket_size,
                "velocity": round(velocities[i], 2),
                "hype": round(hype_buckets[i], 1)
            })

        # Sort candidate clips by highest hype score
        candidate_clips.sort(key=lambda c: c["hype_score"], reverse=True)

        return {
            "spikes": candidate_clips,
            "timeline": timeline,
            "message_count": total_msgs,
            "mean_velocity": round(mean_vel, 2),
            "threshold": round(threshold, 2)
        }

class LiveChatStreamReader:
    """Read live chat continuously from a live YouTube broadcast."""
    def __init__(self, video_id: str, on_message: Optional[callable] = None):
        self.video_id = video_id
        self.on_message = on_message
        self.messages: List[Dict[str, Any]] = []
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self.start_timestamp = time.time()

    def start(self):
        self.is_running = True
        self.start_timestamp = time.time()

        def _worker():
            try:
                chat = pytchat.create(video_id=self.video_id)
                logger.info(f"Connected to live chat for video {self.video_id}")
                while chat.is_alive() and self.is_running:
                    for c in chat.get().sync_items():
                        relative_sec = time.time() - self.start_timestamp
                        item = {
                            "time_in_seconds": relative_sec,
                            "datetime": c.datetime,
                            "author": c.author.name,
                            "message": c.message
                        }
                        self.messages.append(item)
                        if self.on_message:
                            self.on_message(item)
                    time.sleep(1.0)
            except Exception as e:
                logger.error(f"Error in LiveChatStreamReader: {e}")
            finally:
                self.is_running = False

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stop(self) -> List[Dict[str, Any]]:
        self.is_running = False
        return self.messages

def fetch_chat_replay(video_id: str, max_messages: int = 15000) -> List[Dict[str, Any]]:
    """Fetch chat replay from past YouTube live stream VOD."""
    messages = []
    try:
        chat = pytchat.create(video_id=video_id)
        while chat.is_alive() and len(messages) < max_messages:
            items = chat.get().sync_items()
            if not items:
                break
            for c in items:
                # pytchat provides elapsed_time string like '12:34'
                elapsed_str = getattr(c, "elapsed_time", "")
                parts = [int(p) for p in elapsed_str.split(":") if p.isdigit()]
                seconds = 0
                if len(parts) == 3:
                    seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
                elif len(parts) == 2:
                    seconds = parts[0] * 60 + parts[1]
                elif len(parts) == 1:
                    seconds = parts[0]

                messages.append({
                    "time_in_seconds": float(seconds),
                    "author": c.author.name,
                    "message": c.message
                })
    except Exception as e:
        logger.warning(f"Could not load chat replay for {video_id}: {e}")
        
    return messages
