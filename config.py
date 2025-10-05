import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB Configuration
MONGODB_SETTINGS = {
    'host': os.getenv('MONGODB_HOST', 'localhost'),
    'port': int(os.getenv('MONGODB_PORT', 27017)),
    'database': os.getenv('MONGODB_DATABASE', 'kalkulis_inventory'),
    'username': os.getenv('MONGODB_USERNAME', ''),
    'password': os.getenv('MONGODB_PASSWORD', ''),
    'auth_source': os.getenv('MONGODB_AUTH_SOURCE', 'admin'),
    'maxPoolSize': int(os.getenv('MONGODB_MAX_POOL_SIZE', 100)),
    'minPoolSize': int(os.getenv('MONGODB_MIN_POOL_SIZE', 10)),
    'maxIdleTimeMS': int(os.getenv('MONGODB_MAX_IDLE_TIME', 45000)),
}

# Application Settings
APP_SETTINGS = {
    'SECRET_KEY': os.getenv('SECRET_KEY', 'your-secret-key-here'),
    'SESSION_TIMEOUT': int(os.getenv('SESSION_TIMEOUT', 3600)),  # 1 hour
    'ITEMS_PER_PAGE': int(os.getenv('ITEMS_PER_PAGE', 20)),
    'MAX_LOGIN_ATTEMPTS': int(os.getenv('MAX_LOGIN_ATTEMPTS', 5)),
    'LOCKOUT_DURATION': int(os.getenv('LOCKOUT_DURATION', 900)),  # 15 minutes
}

# Real-time Settings
REALTIME_SETTINGS = {
    'ENABLE_REALTIME': os.getenv('ENABLE_REALTIME', 'true').lower() == 'true',
    'CHANGE_STREAM_ENABLED': os.getenv('CHANGE_STREAM_ENABLED', 'true').lower() == 'true',
    'NOTIFICATION_ENABLED': os.getenv('NOTIFICATION_ENABLED', 'true').lower() == 'true',
}

# Logging Configuration
LOGGING_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': os.getenv('LOG_FILE', 'kalkulis.log'),
}