from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class BetBase(BaseModel):
    date: datetime
    tournament: str
    team1: str
    team2: str
    bet_type: str
    total_value: float
    game_score: Optional[str] = None
    is_premium: bool = False
    screenshot_url: Optional[str] = None

class BetCreate(BetBase):
    pass

class Bet(BetBase):
    id: int
    result: Optional[str] = None
    profit: Optional[float] = None
    points: Optional[int] = None
    nominal: Optional[float] = None
    bank: Optional[float] = None
    season: Optional[str] = None
    
    class Config:
        from_attributes = True