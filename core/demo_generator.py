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

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# OSM amenity/tag types that represent realistic field service job sites
_OVERPASS_QUERY_TEMPLATE = """[out:json][timeout:10];
(
  node["office"]({bbox});
  node["amenity"="hospital"]({bbox});
  node["amenity"="clinic"]({bbox});
  node["amenity"="school"]({bbox});
  node["amenity"="university"]({bbox});
  node["amenity"="bank"]({bbox});
  node["amenity"="hotel"]({bbox});
  node["amenity"="factory"]({bbox});
  node["amenity"="marketplace"]({bbox});
  way["office"]({bbox});
  way["amenity"="hospital"]({bbox});
  way["amenity"="clinic"]({bbox});
  way["amenity"="school"]({bbox});
  way["building"="commercial"]({bbox});
  way["building"="office"]({bbox});
  way["building"="industrial"]({bbox});
  way["building"="retail"]({bbox});
);
out center {limit};"""

_NOMINATIM_SEARCH_TERMS = ["office", "hospital", "factory", "clinic", "mall", "industrial park"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _parse_overpass_element(el):
    tags = el.get("tags", {})
    name = tags.get("name:en") or tags.get("name")
    if not name:
        return None

    if el["type"] == "node":
        lat, lon = el.get("lat"), el.get("lon")
    else:
        center = el.get("center", {})
        lat, lon = center.get("lat"), center.get("lon")

    if lat is None or lon is None:
        return None

    # Build address from OSM addr:* tags when available
    num = tags.get("addr:housenumber", "")
    street = tags.get("addr:street", "")
    city = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village") or ""
    parts = []
    if num and street:
        parts.append(f"{num} {street}")
    elif street:
        parts.append(street)
    if city:
        parts.append(city)
    address = ", ".join(parts) if parts else name

    return {"name": name, "lat": round(lat, 6), "lon": round(lon, 6), "address": address}


# ---------------------------------------------------------------------------
# POI fetching strategies
# ---------------------------------------------------------------------------

def _fetch_overpass(bbox):
    south, north, west, east = bbox
    # Overpass bbox order: south,west,north,east
    bbox_str = f"{south},{west},{north},{east}"
    query = _OVERPASS_QUERY_TEMPLATE.format(bbox=bbox_str, limit=200)

    resp = requests.post(
        _OVERPASS_URL,
        data={"data": query},
        headers={"User-Agent": "cuopt-vrp-demo/1.0"},
        timeout=15,
    )
    resp.raise_for_status()

    pois = []
    seen = set()
    for el in resp.json().get("elements", []):
        poi = _parse_overpass_element(el)
        if poi is None:
            continue
        key = (round(poi["lat"], 4), round(poi["lon"], 4))
        if key in seen:
            continue
        seen.add(key)
        pois.append(poi)

    return pois


def _fetch_nominatim_pois(city_name, bbox):
    south, north, west, east = bbox
    # Nominatim viewbox: left(west), top(north), right(east), bottom(south)
    viewbox = f"{west},{north},{east},{south}"

    pois = []
    seen = set()

    for term in _NOMINATIM_SEARCH_TERMS:
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": f"{term} {city_name}",
                    "format": "json",
                    "limit": 20,
                    "viewbox": viewbox,
                    "bounded": 1,
                    "addressdetails": 1,
                },
                headers={"User-Agent": "cuopt-vrp-demo/1.0"},
                timeout=8,
            )
            resp.raise_for_status()
            for item in resp.json():
                lat = round(float(item["lat"]), 6)
                lon = round(float(item["lon"]), 6)
                key = (round(lat, 4), round(lon, 4))
                if key in seen:
                    continue
                seen.add(key)
                addr = item.get("address", {})
                name = item.get("display_name", "").split(",")[0].strip() or term.title()
                street = addr.get("road", "")
                city = addr.get("city") or addr.get("town") or addr.get("village") or ""
                address = ", ".join(p for p in [street, city] if p) or name
                pois.append({"name": name, "lat": lat, "lon": lon, "address": address})
        except Exception as e:
            logger.debug(f"Nominatim term '{term}' failed: {e}")
            continue

        if len(pois) >= 60:
            break

    return pois


def _get_poi_locations(city_name, bbox, num_needed):
    """Return (poi_list, source) using Overpass → Nominatim → random fallback chain."""
    min_acceptable = max(num_needed // 2, 3)

    try:
        pois = _fetch_overpass(bbox)
        if len(pois) >= min_acceptable:
            logger.info(f"Overpass returned {len(pois)} POIs for '{city_name}'")
            return pois, "overpass"
        logger.warning(f"Overpass returned only {len(pois)} POIs (need {min_acceptable}), trying Nominatim")
    except Exception as e:
        logger.warning(f"Overpass failed for '{city_name}': {e}")

    try:
        pois = _fetch_nominatim_pois(city_name, bbox)
        if len(pois) >= min_acceptable:
            logger.info(f"Nominatim returned {len(pois)} POIs for '{city_name}'")
            return pois, "nominatim"
        logger.warning(f"Nominatim returned only {len(pois)} POIs, falling back to random")
    except Exception as e:
        logger.warning(f"Nominatim POI search failed for '{city_name}': {e}")

    return [], "random"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_demo_data(city: str, num_orders: int, num_technicians: int) -> dict:
    display_name, bbox = _geocode(city)
    bbox = _shrink_bbox(bbox)
    short_city = display_name.split(",")[0].strip()

    # Fetch real POI locations for work orders
    poi_locations, source = _get_poi_locations(short_city, bbox, num_orders)

    # Assign skills to technicians, guaranteeing every skill type is covered
    # by at least one technician so work orders are always satisfiable.
    all_skills = list(_SKILLS)
    random.shuffle(all_skills)
    skill_assignments = [[] for _ in range(num_technicians)]
    for idx, skill in enumerate(all_skills):
        skill_assignments[idx % num_technicians].append(skill)
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
        # Pick location: sample from POIs with replacement, or fall back to random point
        if poi_locations:
            poi = random.choice(poi_locations)
            lat, lon = poi["lat"], poi["lon"]
            customer_name = poi["name"]
            address = poi["address"]
        else:
            lat, lon = _random_point(bbox)
            customer_name = _random_company()
            address = short_city

        work_type = random.choice(work_types)
        priority = _weighted_choice(_PRIORITIES)
        candidates = [s for s in _WORK_TYPE_SKILLS[work_type] if s in covered_skills]
        skill = random.choice(candidates if candidates else list(covered_skills))
        svc_min, svc_max = _SERVICE_RANGE[work_type]
        service_time = random.randrange(svc_min, svc_max + 1, 15)

        work_orders.append({
            "id": f"WO{i + 1:03d}",
            "customer_name": customer_name,
            "location": {"latitude": lat, "longitude": lon, "address": address},
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
        "source": source,
        "technicians": technicians,
        "work_orders": work_orders,
    }
