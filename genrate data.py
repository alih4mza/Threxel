import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random

# Set random seed for reproducibility
np.random.seed(42)
random.seed(42)

# Configuration
NUM_EMPLOYEES = 2000
SAMPLES_PER_EMPLOYEE = 24
TOTAL_SAMPLES = NUM_EMPLOYEES * SAMPLES_PER_EMPLOYEE
ANOMALY_RATIO = 0.1  # 10% anomalous
OUTPUT_FILE = "employee_behavior_data.csv"
NORMAL_HOURS = range(9, 17)  # 9:00 AM to 5:00 PM
NORMAL_LOCATION = "Bahawalpur"
OTHER_LOCATIONS = ["Lahore", "Karachi", "Islamabad", "Faisalabad", "Rawalpindi"]
DAILY_DATA_LIMIT_MB = 10240  # 10 GB
BASE_DATE = datetime(2025, 5, 15)  # Base date for timestamps

# Normal behavior distributions
normal_dist = {
    'cpu': {'mean': 30, 'std': 15, 'min': 5, 'max': 90},
    'memory_percent': {'mean': 50, 'std': 15, 'min': 20, 'max': 80},
    'disk_percent': {'mean': 60, 'std': 15, 'min': 30, 'max': 90},
    'network_sent': {'mean': 100, 'std': 50, 'min': 10, 'max': 300},  # MB per hour
    'network_received': {'mean': 100, 'std': 50, 'min': 10, 'max': 300},
    'process_count': {'mean': 50, 'std': 20, 'min': 20, 'max': 100},
    'is_suspicious': {'prob': 0.05}
}

# Anomalous behavior distributions
anomaly_dist = {
    'cpu': {'mean': 95, 'std': 5, 'min': 90, 'max': 100},
    'memory_percent': {'mean': 85, 'std': 10, 'min': 70, 'max': 100},
    'disk_percent': {'mean': 85, 'std': 10, 'min': 70, 'max': 100},
    'network_sent': {'mean': 600, 'std': 200, 'min': 300, 'max': 1000},  # Higher for anomalies
    'network_received': {'mean': 600, 'std': 200, 'min': 300, 'max': 1000},
    'process_count': {'mean': 150, 'std': 30, 'min': 100, 'max': 200},
    'is_suspicious': {'prob': 0.5}
}

def generate_timestamp(is_anomaly):
    """Generate a timestamp (normal: 9 AM–5 PM, anomalous: outside)."""
    if is_anomaly:
        # Outside 9 AM–5 PM (e.g., 12 AM–9 AM or 5 PM–12 AM)
        hour = random.choice([h for h in range(24) if h not in NORMAL_HOURS])
    else:
        hour = random.choice(NORMAL_HOURS)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return BASE_DATE.replace(hour=hour, minute=minute, second=second)

def generate_sample(is_anomaly, daily_data_used):
    """Generate a single sample based on normal or anomalous distributions."""
    dist = anomaly_dist if is_anomaly else normal_dist
    sample = {}
    
    # Generate metrics
    for feature, params in dist.items():
        if feature == 'is_suspicious':
            sample[feature] = 1 if random.random() < params['prob'] else 0
        else:
            value = np.random.normal(params['mean'], params['std'])
            value = max(params['min'], min(params['max'], value))
            sample[feature] = round(value, 2)
    
    # Timestamp
    sample['timestamp'] = generate_timestamp(is_anomaly).strftime("%Y-%m-%d %H:%M:%S")
    
    # Location
    sample['location'] = random.choice(OTHER_LOCATIONS) if is_anomaly else NORMAL_LOCATION
    
    # Adjust network usage to respect daily data limit
    if not is_anomaly:
        # Ensure total daily usage doesn't exceed 10 GB
        max_allowed = (DAILY_DATA_LIMIT_MB - daily_data_used) / (SAMPLES_PER_EMPLOYEE * 0.5)  # Conservative
        sample['network_sent'] = min(sample['network_sent'], max_allowed)
        sample['network_received'] = min(sample['network_received'], max_allowed)
    
    return sample

# Generate synthetic data
data = []
num_anomalies = int(TOTAL_SAMPLES * ANOMALY_RATIO)
num_normal = TOTAL_SAMPLES - num_anomalies

# Track daily data usage per employee
daily_data_usage = {f"emp_{i+1:04d}": 0 for i in range(NUM_EMPLOYEES)}
employee_samples = {eid: [] for eid in daily_data_usage}

# Generate samples per employee
for emp_idx in range(NUM_EMPLOYEES):
    emp_id = f"emp_{emp_idx+1:04d}"
    is_anomaly = random.random() < ANOMALY_RATIO  # Decide if employee has anomalous behavior
    for _ in range(SAMPLES_PER_EMPLOYEE):
        sample = generate_sample(is_anomaly, daily_data_usage[emp_id])
        employee_samples[emp_id].append(sample)
        daily_data_usage[emp_id] += sample['network_sent'] + sample['network_received']

# Flatten samples and shuffle
for emp_id, samples in employee_samples.items():
    for sample in samples:
        sample['employee_id'] = emp_id
        data.append(sample)
random.shuffle(data)

# Create DataFrame
df = pd.DataFrame(data)

# Reorder columns
columns = ['employee_id', 'timestamp', 'location', 'cpu', 'memory_percent', 
           'disk_percent', 'network_sent', 'network_received', 'process_count', 'is_suspicious']
df = df[columns]

# Save to CSV
df.to_csv(OUTPUT_FILE, index=False)
print(f"Synthetic data saved to {OUTPUT_FILE}")
print(f"Total samples: {len(df)}")
print(f"Normal samples (approx): {num_normal}")
print(f"Anomalous samples (approx): {num_anomalies}")

# Validate daily data usage
daily_usage = df.groupby('employee_id')[['network_sent', 'network_received']].sum()
daily_usage['total_mb'] = daily_usage['network_sent'] + daily_usage['network_received']
anomalous_usage = daily_usage[daily_usage['total_mb'] > DAILY_DATA_LIMIT_MB]
print(f"Employees exceeding 10 GB: {len(anomalous_usage)}")