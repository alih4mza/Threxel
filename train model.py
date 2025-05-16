import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib

# Configuration
DATA_FILE = "employee_behavior_data.csv"
MODEL_FILE = "anomaly_model.pkl"
CONTAMINATION = 0.1  # Expected anomaly ratio

# Load data
print("Loading synthetic data...")
df = pd.read_csv(DATA_FILE)

# Select features for training (exclude employee_id, timestamp, location)
features = ['cpu', 'memory_percent', 'disk_percent', 'network_sent', 
            'network_received', 'process_count', 'is_suspicious']
X = df[features].values

# Initialize and train model
print("Training Isolation Forest model...")
model = IsolationForest(contamination=CONTAMINATION, random_state=42, n_estimators=100)
model.fit(X)

# Save model
joblib.dump(model, MODEL_FILE)
print(f"Model saved to {MODEL_FILE}")

# Validate model
print("Validating model...")
scores = -model.decision_function(X)
anomaly_scores = (scores + 1) / 2  # Normalize to [0, 1]
predicted_anomalies = model.predict(X)
num_anomalies = np.sum(predicted_anomalies == -1)
print(f"Predicted anomalies: {num_anomalies} ({num_anomalies/len(X)*100:.2f}%)")
print(f"Average anomaly score: {np.mean(anomaly_scores):.3f}")