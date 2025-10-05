import streamlit as st
import bcrypt
from .database import MongoDBConnection
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger(__name__)

def hash_password(password):
    """Hash a password for storing"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(stored_password, provided_password):
    """Verify a stored password against one provided by user"""
    # Convert stored_password to bytes if it's a string
    if isinstance(stored_password, str):
        stored_password = stored_password.encode('utf-8')
    
    # Ensure provided_password is bytes
    provided_password = provided_password.encode('utf-8') if isinstance(provided_password, str) else provided_password
    
    return bcrypt.checkpw(provided_password, stored_password)

def login_user(username, password):
    """Authenticate a user and return user data if successful"""
    try:
        db = MongoDBConnection.get_database()
        
        # Get user from database
        user = db.users.find_one({"username": username})
        
        if user and verify_password(user['password'], password):
            # Update last login
            db.users.update_one(
                {"_id": user['_id']},
                {"$set": {"last_login": datetime.utcnow()}}
            )
            
            # Store user info in session state
            st.session_state['authenticated'] = True
            st.session_state['user'] = {
                'id': str(user['_id']),
                'username': user['username'],
                'full_name': user['full_name'],
                'role': user['role'],
                'department': user.get('department', ''),
                'is_active': user.get('is_active', True)
            }
            
            logger.info(f"User {username} logged in successfully")
            return True
        else:
            logger.warning(f"Failed login attempt for username: {username}")
            return False
            
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return False

def logout_user():
    """Log out the current user"""
    try:
        if 'user' in st.session_state:
            username = st.session_state['user']['username']
            logger.info(f"User {username} logged out")
            
        st.session_state['authenticated'] = False
        if 'user' in st.session_state:
            del st.session_state['user']
            
    except Exception as e:
        logger.error(f"Error during logout: {e}")

def require_auth():
    """Require authentication to access a page"""
    if not st.session_state.get('authenticated', False):
        st.warning('You need to log in to access this page.')
        st.stop()

def require_role(roles):
    """Require specific role(s) to access a page"""
    require_auth()
    user_role = st.session_state['user']['role']
    if isinstance(roles, str):
        roles = [roles]
    
    if user_role not in roles:
        st.error('You do not have permission to access this page.')
        st.stop()

def create_user(username, password, full_name, role, department=None):
    """Create a new user"""
    try:
        db = MongoDBConnection.get_database()
        
        hashed_password = hash_password(password)
        
        new_user = {
            "username": username,
            "password": hashed_password,
            "full_name": full_name,
            "role": role,
            "department": department,
            "created_at": datetime.utcnow(),
            "is_active": True,
            "last_login": None
        }
        
        result = db.users.insert_one(new_user)
        
        if result.inserted_id:
            logger.info(f"User {username} created successfully")
            return True
        else:
            logger.error(f"Failed to create user {username}")
            return False
            
    except Exception as e:
        logger.error(f"Error creating user {username}: {e}")
        return False

def register_user(username, password, full_name, role, department=None):
    """
    Register a new user in the database
    
    Args:
        username (str): Username for the new user
        password (str): Password for the new user
        full_name (str): Full name of the new user
        role (str): Role of the new user (admin, staff, etc.)
        department (str, optional): Department for the new user
        
    Returns:
        tuple: (success, message)
    """
    try:
        db = MongoDBConnection.get_database()
        
        # Check if username already exists
        existing_user = db.users.find_one({"username": username})
        
        if existing_user:
            logger.warning(f"Registration failed: Username {username} already exists")
            return False, "Username sudah digunakan"
        
        # Hash the password
        hashed_password = hash_password(password)
        
        # Create new user document
        new_user = {
            "username": username,
            "password": hashed_password,
            "full_name": full_name,
            "role": role,
            "department": department,
            "created_at": datetime.utcnow(),
            "is_active": True,
            "last_login": None
        }
        
        # Insert into database
        result = db.users.insert_one(new_user)
        
        if result.inserted_id:
            logger.info(f"User {username} registered successfully")
            return True, "Pengguna baru berhasil didaftarkan"
        else:
            logger.error(f"Failed to register user {username}")
            return False, "Gagal mendaftarkan pengguna baru"
            
    except Exception as e:
        logger.error(f"Error registering user {username}: {e}")
        return False, f"Error: {str(e)}"

def get_user_by_username(username):
    """Get user by username"""
    try:
        db = MongoDBConnection.get_database()
        user = db.users.find_one({"username": username})
        
        if user:
            # Convert ObjectId to string for JSON serialization
            user['_id'] = str(user['_id'])
            return user
        return None
        
    except Exception as e:
        logger.error(f"Error getting user {username}: {e}")
        return None

def get_user_by_id(user_id):
    """Get user by ID"""
    try:
        from bson import ObjectId
        db = MongoDBConnection.get_database()
        
        user = db.users.find_one({"_id": ObjectId(user_id)})
        
        if user:
            # Convert ObjectId to string for JSON serialization
            user['_id'] = str(user['_id'])
            return user
        return None
        
    except Exception as e:
        logger.error(f"Error getting user by ID {user_id}: {e}")
        return None

def update_user(user_id, update_data):
    """Update user data"""
    try:
        from bson import ObjectId
        db = MongoDBConnection.get_database()
        
        # Remove _id if present in update_data
        if '_id' in update_data:
            del update_data['_id']
        
        # Hash password if provided
        if 'password' in update_data:
            update_data['password'] = hash_password(update_data['password'])
        
        # Add updated timestamp
        update_data['updated_at'] = datetime.utcnow()
        
        result = db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            logger.info(f"User {user_id} updated successfully")
            return True
        else:
            logger.warning(f"No changes made to user {user_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        return False

def delete_user(user_id):
    """Delete user (soft delete by setting is_active to False)"""
    try:
        from bson import ObjectId
        db = MongoDBConnection.get_database()
        
        result = db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": False, "deleted_at": datetime.utcnow()}}
        )
        
        if result.modified_count > 0:
            logger.info(f"User {user_id} deleted (soft delete) successfully")
            return True
        else:
            logger.warning(f"No changes made to user {user_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        return False

def get_all_users(limit=100, skip=0, include_inactive=False):
    """Get all users with pagination"""
    try:
        db = MongoDBConnection.get_database()
        
        filter_query = {}
        if not include_inactive:
            filter_query["is_active"] = True
        
        users = list(db.users.find(filter_query).skip(skip).limit(limit))
        
        # Convert ObjectId to string for JSON serialization
        for user in users:
            user['_id'] = str(user['_id'])
        
        return users
        
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

def check_user_permissions(required_roles=None, required_permissions=None):
    """Check if current user has required roles or permissions"""
    if not st.session_state.get('authenticated', False):
        return False
    
    user = st.session_state.get('user', {})
    
    if required_roles:
        if isinstance(required_roles, str):
            required_roles = [required_roles]
        if user.get('role') not in required_roles:
            return False
    
    if required_permissions:
        # This can be extended to check specific permissions
        user_permissions = user.get('permissions', [])
        if not all(perm in user_permissions for perm in required_permissions):
            return False
    
    return True