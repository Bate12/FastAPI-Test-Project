from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import json

app = FastAPI(title="XAMPP API", version="1.0")
engine = create_engine("mysql+pymysql://root:@127.0.0.1:3306/Users")

USE_REDIRECT_DELAY = False
class Color:
    ERROR = "\033[91m"
    SUCCESS = "\033[92m"
    STOP = "\033[0m"


# class for handling creation
class UserCreate(BaseModel):
    name: str = "John Doe"
    signup_ts: datetime | None = None
    friends: list[int] = []

# class for handling responses
class UserResponse (UserCreate):
    id: int


# GET endpoint to check if the server is running
@app.get("/", include_in_schema = False)
def read_root():
    if USE_REDIRECT_DELAY:
        html = '<meta http-equiv="refresh" content="5;url=/docs"/> Redirecting in 5 seconds...'
        return HTMLResponse(content=html, status_code=200)
    
    return RedirectResponse(url="/docs")


# A POST endpoint to receive user data
@app.post("/users/create")
def create_user(user: UserCreate):
    print("POST /users/create is Running")
    try:
        with engine.connect() as conn:
            # Create table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users_table (
                    id INT AUTO_INCREMENT PRIMARY KEY, 
                    name VARCHAR(255),
                    signup_ts DATETIME,
                    friends TEXT
                )
            """))
            
            # Format and insert data
            friends_str = json.dumps(user.friends)
            query = text("""
                INSERT INTO users_table (name, signup_ts, friends) 
                VALUES (:name, :signup_ts, :friends)
            """)
            
            result = conn.execute(query, { 
                "name": user.name, 
                "signup_ts": user.signup_ts, 
                "friends": friends_str
            })
            conn.commit()

            new_id = result.lastrowid
            
            print(f"\n{Color.SUCCESS}id: {new_id} name: {user.name} Successfully saved to Database!{Color.STOP}")
            
        return {"status": "success", "message": f"User {user.name} saved!"}
        
    except Exception as e:
        print(f"\n{Color.ERROR}POST USER ERROR > \n{e}{Color.STOP}")

        raise HTTPException(status_code=400, detail="Database error")
    

# GET all users or GET users 0 to limit, if limit < 0, raise 422 (assuming id starts at 0)
@app.get("/users")
def get_users(limit: int | None = Query(default = None, ge = 0)):
    print("GET /users is Running")
    try:
        with engine.connect() as conn:
            if limit:
                query = text("""
                    SELECT * FROM users_table
                    WHERE id < :limit
                """)
            else:
                query = text("""
                    SELECT * FROM users_table
                """)

            result = conn.execute(query, {
                "limit": limit
            })

            raw_users = result.mappings().fetchall()
            users_data = []
            for row in raw_users:
                user_dict = dict(row)
                if user_dict.get("friends"):
                    user_dict["friends"] = json.loads(user_dict["friends"])

                users_data.append(user_dict)
                
            print(f"\n{Color.SUCCESS}GET Request success, found {len(users_data)} users {Color.STOP}")
            return users_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"\n{Color.ERROR}GET USERS ERROR > \n{e}{Color.STOP}")
        raise HTTPException(status_code=500, detail="Database error")
    

# GET endpoint to fetch user data by id
@app.get("/users/{id}")
def get_user(id : int):
    print("GET /users/{id} is Running")
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT * FROM users_table 
                WHERE id = :id
            """)

            result = conn.execute(query,{
                "id": id
            })
            row = result.mappings().fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            
            user_data = dict(row)
            if user_data.get("friends"):
                user_data["friends"] = json.loads(user_data["friends"])

            print(f"\n{Color.SUCCESS}GET Request success, found user: {user_data["id"]} - {user_data["name"]} {Color.STOP}")
            
            return user_data

    except HTTPException:
        raise
    except Exception as e:
        print(f"\n{Color.ERROR}GET USER BY ID ERROR > \n{e}{Color.STOP}")
        raise HTTPException(status_code=500, detail="Database error")

    
# DELETE a user by id
@app.delete("/users/{id}")
def delete_user(id: int):
    print("DELETE /users/{id} is Running")
    try:
        with engine.connect() as conn:
            query = text("""
                DELETE FROM users_table 
                WHERE id = :id
            """)

            result = conn.execute(query, {
                "id": id
            })
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"user id: {id} not found")
            
            conn.commit()

            print(f"\n{Color.SUCCESS}User id: {id} deleted success {Color.STOP}")
            return {"status": "success", "message": f"User {id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"\n{Color.ERROR}DELETE USER ERROR > \n{e}{Color.STOP}")
        raise HTTPException(status_code=500, detail="Database error")
    
# UPDATE user name
@app.put("/users/{id}")
def update_user_name(id: int, new_name: str):
    print("PUT /users/{id} is Running")
    try:
        with engine.connect() as conn:
            query = text("""
                UPDATE users_table
                SET name = :newName
                WHERE id = :id
            """)

            result = conn.execute(query, {
                "newName": new_name,
                "id": id,
            })

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"user id: {id} not found")
            
            conn.commit()

            print(f"\n{Color.SUCCESS}User id: {id} name changed to {new_name} {Color.STOP}")
            return {"status": "success", "message": f"User {id} name updated to {new_name}"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"\n{Color.ERROR}UPDATE USER NAME ERROR > \n{e}{Color.STOP}")
        raise HTTPException(status_code=500, detail="Database error")
