from database import SessionLocal
from models import Agent, OrganizationAgentMapping

db = SessionLocal()

# Remove old system agent records (agent_03, agent_04)
d1 = db.query(Agent).filter(Agent.id.like('%agent_03%')).delete(synchronize_session=False)
d2 = db.query(Agent).filter(Agent.id.like('%agent_04%')).delete(synchronize_session=False)
d3 = db.query(OrganizationAgentMapping).filter(OrganizationAgentMapping.agent_id.like('%agent_03%')).delete(synchronize_session=False)
d4 = db.query(OrganizationAgentMapping).filter(OrganizationAgentMapping.agent_id.like('%agent_04%')).delete(synchronize_session=False)

# Remove old dedicated_agent_XX and shared_agent_XX records
d5 = db.query(Agent).filter(Agent.id.like('%dedicated_agent_%')).delete(synchronize_session=False)
d6 = db.query(Agent).filter(Agent.id.like('%shared_agent_%')).delete(synchronize_session=False)
d7 = db.query(OrganizationAgentMapping).filter(OrganizationAgentMapping.agent_id.like('%dedicated_agent_%')).delete(synchronize_session=False)
d8 = db.query(OrganizationAgentMapping).filter(OrganizationAgentMapping.agent_id.like('%shared_agent_%')).delete(synchronize_session=False)

db.commit()
db.close()
total = d1+d2+d3+d4+d5+d6+d7+d8
print(f'Deleted {total} old agent records. Re-add your agents via the UI.')
