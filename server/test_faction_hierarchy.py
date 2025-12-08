import pytest
from world import World, Faction, User, CharacterSheet

@pytest.fixture
def world():
    w = World()
    # Create users
    w.create_user("LeaderPC", "pw", "Leader")
    w.create_user("OfficerPC", "pw", "Officer")
    w.create_user("MemberPC", "pw", "Member")
    w.create_user("RecruitPC", "pw", "Recruit")
    w.create_user("OutsiderPC", "pw", "Outsider")
    
    # Create NPCs
    w.get_or_create_npc_id("LeaderNPC")
    w.get_or_create_npc_id("OfficerNPC")
    w.get_or_create_npc_id("MemberNPC")
    w.get_or_create_npc_id("RecruitNPC")
    
    # Create Faction
    f = w.create_faction("The Guild", "Test Guild")
    
    # Add Ranks
    f.add_rank("Grandmaster", 10)
    f.add_rank("Captain", 5)
    f.add_rank("Soldier", 1)
    f.add_rank("Initiate", 0)
    
    # Add Members
    leader_pc = w.get_user_by_display_name("LeaderPC").user_id
    officer_pc = w.get_user_by_display_name("OfficerPC").user_id
    member_pc = w.get_user_by_display_name("MemberPC").user_id
    recruit_pc = w.get_user_by_display_name("RecruitPC").user_id
    
    leader_npc = w.get_or_create_npc_id("LeaderNPC")
    officer_npc = w.get_or_create_npc_id("OfficerNPC")
    member_npc = w.get_or_create_npc_id("MemberNPC")
    recruit_npc = w.get_or_create_npc_id("RecruitNPC")
    
    f.add_member_player(leader_pc)
    f.add_member_player(officer_pc)
    f.add_member_player(member_pc)
    f.add_member_player(recruit_pc)
    
    f.add_member_npc(leader_npc)
    f.add_member_npc(officer_npc)
    f.add_member_npc(member_npc)
    f.add_member_npc(recruit_npc)
    
    # Assign Ranks
    f.set_member_rank(leader_pc, "Grandmaster")
    f.set_member_rank(officer_pc, "Captain")
    f.set_member_rank(member_pc, "Soldier")
    f.set_member_rank(recruit_pc, "Initiate")
    
    f.set_member_rank(leader_npc, "Grandmaster")
    f.set_member_rank(officer_npc, "Captain")
    f.set_member_rank(member_npc, "Soldier")
    f.set_member_rank(recruit_npc, "Initiate")
    
    return w

def test_promote_logic(world):
    f = world.get_faction_by_name("The Guild")
    
    leader_pc = world.get_user_by_display_name("LeaderPC").user_id
    officer_pc = world.get_user_by_display_name("OfficerPC").user_id
    member_pc = world.get_user_by_display_name("MemberPC").user_id
    
    # Leader (10) can promote Member (1) to Captain (5)
    assert f.can_promote(leader_pc, member_pc, "Captain")
    
    # Officer (5) cannot promote Member (1) to Captain (5) (cannot promote to equal)
    assert not f.can_promote(officer_pc, member_pc, "Captain")
    
    # Officer (5) cannot promote Member (1) to Grandmaster (10) (cannot promote above self)
    assert not f.can_promote(officer_pc, member_pc, "Grandmaster")
    
    # Officer (5) cannot promote Leader (10)
    assert not f.can_promote(officer_pc, leader_pc, "Grandmaster")

def test_demote_logic(world):
    f = world.get_faction_by_name("The Guild")
    
    leader_pc = world.get_user_by_display_name("LeaderPC").user_id
    officer_pc = world.get_user_by_display_name("OfficerPC").user_id
    member_pc = world.get_user_by_display_name("MemberPC").user_id
    
    # Leader (10) can demote Officer (5) to Soldier (1)
    assert f.can_demote(leader_pc, officer_pc, "Soldier")
    
    # Officer (5) can demote Member (1) to Initiate (0)
    assert f.can_demote(officer_pc, member_pc, "Initiate")
    
    # Officer (5) cannot demote Leader (10)
    assert not f.can_demote(officer_pc, leader_pc, "Soldier")
    
    # Equal rank demotion: Officer (5) can demote another Officer (5)?
    # The rule was "equal or higher status".
    # Let's create another officer
    world.create_user("Officer2", "pw", "Officer2")
    off2 = world.get_user_by_display_name("Officer2").user_id
    f.add_member_player(off2)
    f.set_member_rank(off2, "Captain")
    
    assert f.can_demote(officer_pc, off2, "Soldier")

def test_npc_hierarchy(world):
    f = world.get_faction_by_name("The Guild")
    
    leader_npc = world.get_or_create_npc_id("LeaderNPC")
    member_pc = world.get_user_by_display_name("MemberPC").user_id
    
    # NPC Leader (10) can promote PC Member (1)
    assert f.can_promote(leader_npc, member_pc, "Captain")
    
    # NPC Leader (10) can demote PC Member (1)
    assert f.can_demote(leader_npc, member_pc, "Initiate")

def test_induct_logic(world):
    f = world.get_faction_by_name("The Guild")
    
    leader_pc = world.get_user_by_display_name("LeaderPC").user_id
    officer_pc = world.get_user_by_display_name("OfficerPC").user_id
    member_pc = world.get_user_by_display_name("MemberPC").user_id
    
    # Default leadership threshold is 5
    
    # Leader (10) can induct
    assert f.can_induct(leader_pc)
    
    # Officer (5) can induct
    assert f.can_induct(officer_pc)
    
    # Member (1) cannot induct
    assert not f.can_induct(member_pc)
    
    # Change threshold
    f.leadership_threshold = 6
    assert not f.can_induct(officer_pc)
