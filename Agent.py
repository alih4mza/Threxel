import socketio
import psutil
import time
import platform
import os
import sys
import json
from datetime import datetime
import threading
import logging
import numpy as np
import joblib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Socket.IO client
sio = socketio.Client(reconnection=True, reconnection_attempts=10, reconnection_delay=2, reconnection_delay_max=10)

# Agent configuration
AGENT_ID = "agent_001"
SERVER_URL = "https://www.threxel.com"
SYSTEM_NAME = platform.node()
VERSION = "1.0.0"
CURRENT_USER = os.getlogin()
MODEL_FILE = "anomaly_model.pkl"
NORMAL_HOURS = range(9, 17)  # 9:00 AM to 5:00 PM
NORMAL_LOCATION = "Bahawalpur"
DAILY_DATA_LIMIT_MB = 10240  # 10 GB

# Load pre-trained model
try:
    model = joblib.load(MODEL_FILE)
    logger.info("Loaded pre-trained anomaly detection model")
except Exception as e:
    logger.error(f"Error loading model: {e}")
    model = None

# Track daily data usage
daily_data_usage = 0
last_reset = datetime.now()

# File system event handler
class FileEventHandler(FileSystemEventHandler):
    def __init__(self, log_callback):
        self.log_callback = log_callback

    def on_created(self, event):
        if not event.is_directory:
            self.log_callback("File Created", f"File: {event.src_path}", 0.0, [])

    def on_modified(self, event):
        if not event.is_directory:
            self.log_callback("File Modified", f"File: {event.src_path}", 0.0, [])

    def on_deleted(self, event):
        if not event.is_directory:
            self.log_callback("File Deleted", f"File: {event.src_path}", 0.0, [])

def detect_anomaly(features, timestamp, location):
    """Detect anomalies using the pre-trained model and rule-based checks."""
    if model is None:
        logger.warning("No model loaded, returning default values")
        return 0.0, []
    try:
        features = np.array(features).reshape(1, -1)
        prediction = model.predict(features)
        score = -model.decision_function(features)[0]
        anomaly_score = min(max((score + 1) / 2, 0), 1)
        alerts = ["Suspicious activity"] if prediction[0] == -1 else []
        
        hour = timestamp.hour
        if hour not in NORMAL_HOURS:
            anomaly_score = max(anomaly_score, 0.5)
            alerts.append("Usage outside 9 AM–5 PM")
        if location != NORMAL_LOCATION:
            anomaly_score = max(anomaly_score, 0.5)
            alerts.append(f"Usage outside {NORMAL_LOCATION}")
        global daily_data_usage
        if daily_data_usage > DAILY_DATA_LIMIT_MB:
            anomaly_score = max(anomaly_score, 0.5)
            alerts.append("Data usage exceeds 10 GB")
        
        return anomaly_score, alerts
    except Exception as e:
        logger.error(f"Error detecting anomaly: {e}")
        return 0.0, []

# Function to get system performance metrics
def get_system_metrics():
    global daily_data_usage, last_reset
    try:
        now = datetime.now()
        if now.date() > last_reset.date():
            daily_data_usage = 0
            last_reset = now
        
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        network = psutil.net_io_counters()
        
        network_sent = getattr(network, 'bytes_sent', 0) / (1024 * 1024)  # MB
        network_recv = getattr(network, 'bytes_recv', 0) / (1024 * 1024)  # MB
        daily_data_usage += network_sent + network_recv
        
        metrics = {
            'cpu': cpu_usage,
            'memory_percent': memory.percent,
            'disk_percent': disk.percent,
            'network_sent': network_sent,
            'network_received': network_recv
        }
        
        location = NORMAL_LOCATION  # Replace with geolocation if available
        timestamp = now
        
        features = [
            metrics['cpu'],
            metrics['memory_percent'],
            metrics['disk_percent'],
            metrics['network_sent'],
            metrics['network_received'],
            len(psutil.pids()),
            0  # Default is_suspicious
        ]
        
        anomaly_score, alerts = detect_anomaly(features, timestamp, location)
        if anomaly_score > 0.3:
            logs.append(log_activity(
                "System Metrics Anomaly",
                f"Metrics: CPU={cpu_usage}%, Memory={memory.percent}%, Disk={disk.percent}%, Location={location}",
                anomaly_score,
                alerts
            ))
        
        return metrics
    except Exception as e:
        logger.error(f"Error getting system metrics: {e}")
        return {'cpu': 0, 'memory_percent': 0, 'disk_percent': 0, 'network_sent': 0, 'network_received': 0}

# Function to log activities
def log_activity(activity, details="", anomaly_score=0.0, alerts=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        'timestamp': timestamp,
        'activity': activity,
        'details': details,
        'anomaly_score': anomaly_score,
        'alerts': alerts if alerts else []
    }

# Monitor system events and user activities
def monitor_system_events():
    logs = []
    logs.append(log_activity("System Startup", f"System started by {CURRENT_USER}"))

    def process_monitor():
        known_pids = set()
        while True:
            try:
                current_pids = set(psutil.pids())
                new_pids = current_pids - known_pids
                for pid in new_pids:
                    try:
                        p = psutil.Process(pid)
                        is_suspicious = 1 if any(name in p.name().lower() for name in ["bash", "sh"]) else 0
                        metrics = get_system_metrics()
                        features = [
                            metrics['cpu'],
                            metrics['memory_percent'],
                            metrics['disk_percent'],
                            metrics['network_sent'],
                            metrics['network_received'],
                            len(current_pids),
                            is_suspicious
                        ]
                        anomaly_score, alerts = detect_anomaly(
                            features, 
                            datetime.now(), 
                            NORMAL_LOCATION
                        )
                        logs.append(log_activity(
                            "Process Started",
                            f"Process: {p.name()} (PID: {pid}, Path: {p.exe()}), Location={NORMAL_LOCATION}",
                            anomaly_score,
                            alerts
                        ))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                known_pids = current_pids
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in process monitor: {e}")

    def file_monitor():
        event_handler = FileEventHandler(log_activity)
        observer = Observer()
        observer.schedule(event_handler, path='/home', recursive=True)  # Monitor /home directory
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    threading.Thread(target=process_monitor, daemon=True).start()
    threading.Thread(target=file_monitor, daemon=True).start()
    return logs

# Main loop to send updates
def send_update(logs):
    try:
        if not sio.connected:
            sio.connect(SERVER_URL, wait_timeout=10)
        metrics = get_system_metrics()
        update_data = {
            'agent_id': AGENT_ID,
            'system_name': SYSTEM_NAME,
            'version': VERSION,
            'current_user': CURRENT_USER,
            'status': 'active',
            'performance': metrics,
            'cpu_trend': [metrics['cpu']] * 5,
            'network_traffic': {'daily_usage': metrics['network_sent'] + metrics['network_received']},
            'analysis': {
                'suspicious_patterns': [log['activity'] for log in logs if log['anomaly_score'] > 0.3],
                'risk_score': sum(log['anomaly_score'] for log in logs) * 10
            },
            'logs': logs
        }
        sio.emit('log_update', update_data)
        logger.info(f"Sent update for Agent {AGENT_ID}")
    except Exception as e:
        logger.error(f"Error sending update: {e}")

@sio.event
def connect():
    logger.info(f"Agent {AGENT_ID} connected to server")
    sio.emit('register_agent', {
        'agent_id': AGENT_ID,
        'system_name': SYSTEM_NAME,
        'version': VERSION,
        'current_user': CURRENT_USER,
        'status': 'active'
    })

@sio.event
def disconnect():
    logger.warning(f"Agent {AGENT_ID} disconnected from server")

@sio.event
def connect_error(data):
    logger.error(f"Connection error: {data}")

if __name__ == "__main__":
    try:
        logger.info(f"Attempting to connect Agent {AGENT_ID} to {SERVER_URL}")
        sio.connect(SERVER_URL, wait_timeout=10)
        logs = monitor_system_events()
        while True:
            send_update(logs)
            time.sleep(1)
            logs.append(log_activity(
                "User Activity",
                f"User {CURRENT_USER} performed an action",
                anomaly_score=0.0
            ))
    except KeyboardInterrupt:
        logs.append(log_activity("Agent Stopped", "Agent manually stopped"))
        send_update(logs)
        sio.disconnect()
        logger.info("Agent stopped gracefully")
    except Exception as e:
        logger.error(f"Error in Agent: {e}")
        sio.disconnect()