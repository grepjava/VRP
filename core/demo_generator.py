import math
import random
import logging
import requests

logger = logging.getLogger(__name__)

_FIRST_NAMES = [
    "Ahmad", "Siti", "Muhammad", "Nur", "Abdul", "Farah", "Hafiz", "Zara",
    "Lim", "Tan", "Wong", "Lee", "Ng", "Chen", "Yap", "Chong",
    "Raj", "Kumar", "Priya", "Arun", "Deepa", "Vikram", "Anita",
    "James", "Sarah", "David", "Emma", "Michael", "Jessica", "Daniel",
    "Carlos", "Maria", "Luis", "Ana", "Pedro", "Sofia",
]

_LAST_NAMES = [
    "Rahman", "Abdullah", "Hassan", "Ibrahim", "Ismail", "Yusof", "Razak",
    "Wei Liang", "Chee Keong", "Mei Ling", "Ah Beng", "Siew Ling",
    "Selvam", "Krishnan", "Pillai", "Nair", "Rajan",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Taylor", "Wilson",
    "Garcia", "Martinez", "Hernandez", "Lopez", "Gonzalez",
]

_COMPANY_PREFIXES = [
    "Central", "Grand", "City", "Metro", "Prime", "Elite", "Royal",
    "Premier", "Golden", "Pacific", "Continental", "Capital",
]

_COMPANY_NOUNS = [
    "Plaza", "Tower", "Centre", "Mall", "Hospital", "Hotel",
    "Factory", "Warehouse", "Office Park", "Residence", "Apartments",
    "Complex", "Station", "Terminal", "Clinic", "Gymnasium",
]

_SKILLS = ["electrical", "plumbing", "HVAC", "networking", "mechanical", "inspection"]

_WORK_TYPE_SKILLS = {
    "maintenance": ["HVAC", "mechanical", "electrical"],
    "repair":      ["electrical", "plumbing", "mechanical"],
    "inspection":  ["inspection", "electrical"],
    "installation":["networking", "electrical"],
    "emergency":   ["electrical", "plumbing", "mechanical"],
}

_PRIORITIES = [
    ("emergency", 5),
    ("critical",  10),
    ("high",      30),
    ("medium",    35),
    ("low",       20),
]

_SERVICE_RANGE = {
    "maintenance": (60, 120),
    "repair":      (45, 90),
    "inspection":  (30, 60),
    "installation":(90, 180),
    "emergency":   (30, 60),
}


def _weighted_choice(choices):
    total = sum(w for _, w in choices)
    r = random.uniform(0, total)
    acc = 0
    for val, w in choices:
        acc += w
        if r <= acc:
            return val
    return choices[-1][0]


def _random_name():
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"


def _random_company():
    return f"{random.choice(_COMPANY_PREFIXES)} {random.choice(_COMPANY_NOUNS)}"


def _shrink_bbox(bbox, factor=0.15):
    south, north, west, east = bbox
    dlat = (north - south) * factor
    dlon = (east - west) * factor
    return south + dlat, north - dlat, west + dlon, east - dlon


def _random_point(bbox):
    south, north, west, east = bbox
    return round(random.uniform(south, north), 6), round(random.uniform(west, east), 6)


def _geocode(city: str):
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": city, "format": "json", "limit": 1},
        headers={"User-Agent": "cuopt-vrp-demo/1.0"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"City not found: {city!r}")
    item = results[0]
    bbox = tuple(float(x) for x in item["boundingbox"])
    display = item.get("display_name", city)
    return display, bbox


def generate_demo_data(city: str, num_orders: int, num_technicians: int) -> dict:
    display_name, bbox = _geocode(city)
    bbox = _shrink_bbox(bbox)
    short_city = display_name.split(",")[0].strip()

    # Assign skills to technicians, guaranteeing every skill type is covered
    # by at least one technician so work orders are always satisfiable.
    all_skills = list(_SKILLS)
    random.shuffle(all_skills)
    skill_assignments = [[] for _ in range(num_technicians)]
    # Round-robin one of each skill across technicians
    for idx, skill in enumerate(all_skills):
        skill_assignments[idx % num_technicians].append(skill)
    # Top up technicians that ended up with only one skill
    for sa in skill_assignments:
        if len(sa) < 2:
            extras = [s for s in _SKILLS if s not in sa]
            sa.append(random.choice(extras))

    technicians = []
    for i in range(num_technicians):
        lat, lon = _random_point(bbox)
        skills = skill_assignments[i]
        technicians.append({
            "id": f"TECH{i + 1:03d}",
            "name": _random_name(),
            "start_location": {"latitude": lat, "longitude": lon, "address": short_city},
            "work_shift": {"earliest": 480, "latest": 1020},
            "break_window": {"earliest": 720, "latest": 780},
            "break_duration": 60,
            "skills": skills,
            "max_daily_orders": max(8, math.ceil(num_orders / num_technicians) + 2),
            "max_travel_time": 300,
            "hourly_rate": float(random.randrange(55, 82, 1)),
            "vehicle_type": random.choice(["van", "car"]),
            "drop_return_trip": False,
        })

    covered_skills = {s for tech in technicians for s in tech["skills"]}

    work_types = list(_WORK_TYPE_SKILLS.keys())
    work_orders = []
    for i in range(num_orders):
        lat, lon = _random_point(bbox)
        work_type = random.choice(work_types)
        priority = _weighted_choice(_PRIORITIES)
        candidates = [s for s in _WORK_TYPE_SKILLS[work_type] if s in covered_skills]
        skill = random.choice(candidates if candidates else list(covered_skills))
        svc_min, svc_max = _SERVICE_RANGE[work_type]
        service_time = random.randrange(svc_min, svc_max + 1, 15)
        work_orders.append({
            "id": f"WO{i + 1:03d}",
            "customer_name": _random_company(),
            "location": {"latitude": lat, "longitude": lon, "address": short_city},
            "priority": priority,
            "work_type": work_type,
            "service_time": service_time,
            "required_skills": [skill],
            "description": f"{work_type.capitalize()} job",
            "estimated_value": float(random.randrange(200, 3100, 50)),
            "time_window": None,
        })

    return {
        "city": display_name,
        "technicians": technicians,
        "work_orders": work_orders,
    }
