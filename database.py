# database.py

import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Database filename
DB_FILENAME = 'bot_database.db'

def initialize_database():
    """Initialize the SQLite database and create the users table."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        
        # Create users table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                free_interactions_used INTEGER DEFAULT 0,
                indecent_credits INTEGER DEFAULT 0  -- Set default indecent_credits to 0
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.debug("Database initialized and users table ensured.")
    except Exception as e:
        logger.exception(f"Failed to initialize database: {e}")
        raise

def get_user(user_id):
    """Retrieve user data from the database."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        
        cursor.execute('SELECT free_interactions_used, indecent_credits FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            user_data = {'free_interactions_used': result[0], 'indecent_credits': result[1]}
            logger.debug(f"Retrieved existing user {user_id}: {user_data}")
        else:
            # If user doesn't exist, create a new record with 0 indecent_credits
            cursor.execute('INSERT INTO users (user_id, indecent_credits) VALUES (?, ?)', (user_id, 0))
            conn.commit()
            user_data = {'free_interactions_used': 0, 'indecent_credits': 0}
            logger.debug(f"New user {user_id} created with 0 indecent_credits.")
        
        conn.close()
        return user_data
    except Exception as e:
        logger.exception(f"Error in get_user for user {user_id}: {e}")
        raise

def update_user(user_id, free_interactions_used=None, indecent_credits=None):
    """Update user data in the database."""
    try:
        conn = sqlite3.connect(DB_FILENAME)
        cursor = conn.cursor()
        
        fields = []
        values = []
        
        if free_interactions_used is not None:
            fields.append('free_interactions_used = ?')
            values.append(free_interactions_used)
        
        if indecent_credits is not None:
            fields.append('indecent_credits = ?')
            values.append(indecent_credits)
        
        if fields:
            query = f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?"
            values.append(user_id)
            cursor.execute(query, tuple(values))
            conn.commit()
            logger.debug(f"Updated user {user_id}: free_interactions_used={free_interactions_used}, indecent_credits={indecent_credits}")
        
        conn.close()
    except Exception as e:
        logger.exception(f"Error in update_user for user {user_id}: {e}")
        raise

def add_credits(user_id, credits_to_add):
    """Add Indecent Credits to a user's balance."""
    try:
        user = get_user(user_id)
        new_credits = user['indecent_credits'] + credits_to_add
        update_user(user_id, indecent_credits=new_credits)
        logger.debug(f"Added {credits_to_add} indecent_credits to user {user_id}. New balance: {new_credits}")
    except Exception as e:
        logger.exception(f"Error in add_credits for user {user_id}: {e}")
        raise

def consume_credit(user_id):
    """Consume one Indecent Credit from a user's balance."""
    try:
        user = get_user(user_id)
        if user['indecent_credits'] >= 1:
            new_credits = user['indecent_credits'] - 1
            update_user(user_id, indecent_credits=new_credits)
            logger.debug(f"Consumed 1 indecent_credit from user {user_id}. Remaining credits: {new_credits}")
            return True
        else:
            logger.debug(f"User {user_id} has no indecent_credits to consume.")
            return False
    except Exception as e:
        logger.exception(f"Error in consume_credit for user {user_id}: {e}")
        raise

def increment_free_interactions(user_id):
    """Increment the count of free interactions used by the user."""
    try:
        user = get_user(user_id)
        new_free = user['free_interactions_used'] + 1
        update_user(user_id, free_interactions_used=new_free)
        logger.debug(f"Incremented free interactions for user {user_id}. Total used: {new_free}")
        return new_free
    except Exception as e:
        logger.exception(f"Error in increment_free_interactions for user {user_id}: {e}")
        raise
