import os,sys
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/tutor-test.db')
os.environ.setdefault('REDIS_URL','redis://localhost:9/0')
os.environ.setdefault('JWT_SECRET','test-secret')
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from src.config.database import Base,engine,SessionLocal
class FakeQueue:
    def lpush(self,*a,**k): pass
    def brpop(self,*a,**k): return None
    def ping(self): return True
@pytest.fixture(autouse=True)
def fake_queue(monkeypatch):
    import src.services.calculations as calc_mod
    import src.services.reports as report_mod
    monkeypatch.setattr(calc_mod,'queue',FakeQueue())
    monkeypatch.setattr(report_mod,'queue',FakeQueue())
@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        yield session
