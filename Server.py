from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit
from pymongo import MongoClient
import json
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'  # Change to a strong secret key in production
socketio = SocketIO(app, cors_allowed_origins="*")

# MongoDB Setup
try:
    client = MongoClient('mongodb://localhost:27017/')
    db = client['agent_logs']
    logs_collection = db['logs']
    # Create index for efficient queries
    logs_collection.create_index([("agent_id", 1), ("timestamp", -1)])
    logger.info("Connected to MongoDB and initialized logs collection")
except Exception as e:
    logger.error(f"Error connecting to MongoDB: {e}")
    raise

# Store logs in MongoDB
def store_logs(agent_id, logs):
    try:
        log_documents = [
            {
                'agent_id': agent_id,
                'timestamp': log['timestamp'],
                'activity': log['activity'],
                'details': log['details'],
                'anomaly_score': float(log['anomaly_score']),  # Ensure float
                'alerts': json.dumps(log.get('alerts', []))  # Store as JSON string
            }
            for log in logs
        ]
        if log_documents:
            logs_collection.insert_many(log_documents)
        logger.info(f"Stored {len(logs)} logs for agent {agent_id} in MongoDB")
    except Exception as e:
        logger.error(f"Error storing logs in MongoDB: {e}")

# Get recent 25 logs for an agent
def get_recent_logs(agent_id):
    try:
        logs = []
        cursor = logs_collection.find({'agent_id': agent_id}).sort('timestamp', -1).limit(25)
        for doc in cursor:
            logs.append({
                'timestamp': doc['timestamp'],
                'activity': doc['activity'],
                'details': doc['details'],
                'anomaly_score': doc['anomaly_score'],
                'alerts': json.loads(doc['alerts'])
            })
        logger.info(f"Retrieved {len(logs)} recent logs for agent {agent_id} from MongoDB")
        return logs
    except Exception as e:
        logger.error(f"Error retrieving logs from MongoDB: {e}")
        return []

# In-memory storage for agents
agents = {}

# Routes
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    logger.info("Rendering dashboard")
    return render_template('dashboard.html', agents=agents.values(), current_time=datetime.now().strftime("%H:%M:%S"))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'password':  # Simplified for demo
            session['username'] = username
            logger.info(f"User {username} logged in successfully")
            return redirect(url_for('index'))
        logger.warning(f"Failed login attempt for username {username}")
        return "Invalid credentials", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username', 'unknown')
    session.pop('username', None)
    logger.info(f"User {username} logged out")
    return redirect(url_for('login'))

@app.route('/change_credentials')
def change_credentials():
    logger.info("Accessed change credentials page")
    return "Change credentials page (not implemented)"

# WebSocket events
@socketio.on('register_agent')
def handle_register_agent(data):
    agent_id = data['agent_id']
    agents[agent_id] = {
        'agent_id': agent_id,
        'system_name': data['system_name'],
        'version': data['version'],
        'current_user': data['current_user'],
        'status': data['status'],
        'data_usage': 0,
        'behavior_anomalies': 0,
        'total_logs': 0,
        'peer_deviation': 0,
        'logs': []
    }
    logger.info(f"Agent {agent_id} registered")
    emit('agent_registered', agents[agent_id], broadcast=True)

@socketio.on('log_update')
def handle_log_update(data):
    try:
        agent_id = data['agent_id']
        if agent_id in agents:
            # Store all logs in MongoDB
            store_logs(agent_id, data['logs'])
            
            # Update agent data with recent 25 logs
            recent_logs = get_recent_logs(agent_id)
            agents[agent_id].update({
                'system_name': data['system_name'],
                'version': data['version'],
                'current_user': data['current_user'],
                'status': data['status'],
                'data_usage': data['network_traffic']['daily_usage'],
                'behavior_anomalies': len(data['analysis']['suspicious_patterns']),
                'total_logs': len(recent_logs),
                'peer_deviation': data['analysis']['risk_score'],
                'logs': recent_logs
            })
            data['logs'] = recent_logs  # Update data sent to dashboard
            emit('log_update', data, broadcast=True)
            logger.info(f"Processed log update for agent {agent_id}")

            # Emit alerts if necessary
            for log in data['logs']:
                if log['anomaly_score'] > 0.3:
                    emit('alert', {'message': f"Suspicious activity detected on {agent_id}: {log['activity']}"}, broadcast=True)
                    logger.warning(f"Alert emitted for agent {agent_id}: {log['activity']}")
    except Exception as e:
        logger.error(f"Error handling log update: {e}")

if __name__ == "__main__":
    try:
        logger.info("Starting server...")
        # For production, Gunicorn will be used; this is for testing
        socketio.run(app, debug=False, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Server failed to start: {e}")