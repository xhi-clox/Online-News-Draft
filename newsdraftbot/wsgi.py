import os
from app import app
from scheduler import init_scheduler

init_scheduler(app)
