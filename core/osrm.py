"""
OSRM (Open Source Routing Machine) integration for distance/time matrix calculation
Exact C++ implementation parity - single API calls with fail-fast behavior
"""

import requests
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote
import time
import math

from config import CONFIG
from core.models import Location, DistanceMatrix


logger = logging.getLogger(__name__)

_matrix_cache: Dict[tuple, DistanceMatrix] = {}


class OSRMError(Exception):
    """Custom exception for OSRM-related errors"""
    pass


class OSRMClient:
    """Client for interacting with OSRM server with C++ parity and fail-fast behavior"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize OSRM client"""
        self.config = config or CONFIG['osrm']
        self.base_url = self.config['base_url']
        self.table_endpoint = self.config['table_endpoint']
        self.timeout = self.config['timeout']

        # Match C++ implementation - no artificial limits
        self.max_locations = self.config.get('max_locations_per_request', 500)

        # Use C++ default chunk size exactly
        self.default_chunk_size = 100

        logger.info(f"Initialized OSRM client for {self.base_url}")
        print(f"🌐 OSRM Client initialized: {self.base_url}")
        print(f"🚀 C++ parity mode: max {self.max_locations} locations, chunk size {self.default_chunk_size}")
        print(f"⚡ Fail-fast enabled, no artificial limits")

    def health_check(self) -> bool:
        """Check if OSRM server is accessible and API is working"""
        try:
            # First check if server responds
            response = requests.get(self.base_url, timeout=5)
            if response.status_code not in [200, 400]:
                return False

            # Test with simple coordinates (PJ area)
            test_url = f"{self.base_url}/table/v1/driving/101.5815,3.1084;101.5934,3.0865"
            api_response = requests.get(test_url, timeout=10)

            if api_response.status_code == 200:
                data = api_response.json()
                return data.get('code') == 'Ok'

            return False

        except Exception as e:
            logger.error(f"OSRM health check failed: {e}")
            return False

    def _calculate_chunk_size(self, locations: List[Location]) -> int:
        """Return C++ standard chunk size of 100"""
        print(f"🔒 Using C++ standard chunk size: 100 locations")
        return 100

    def _build_chunked_url(self, locations: List[Location],
                          sources: List[int], destinations: List[int]) -> str:
        """Build OSRM URL for chunked request with length validation"""

        # Validate coordinates
        coord_strings = []
        for i, loc in enumerate(locations):
            if not (-90 <= loc.latitude <= 90):
                raise OSRMError(f"Invalid latitude at location {i}: {loc.latitude}")
            if not (-180 <= loc.longitude <= 180):
                raise OSRMError(f"Invalid longitude at location {i}: {loc.longitude}")

            # Use 5 decimal places for precision (OSRM standard)
            coord_string = f"{loc.longitude:.5f},{loc.latitude:.5f}"
            coord_strings.append(coord_string)

        # Build base URL
        coords_param = ';'.join(coord_strings)
        url = f"{self.base_url}{self.table_endpoint}{coords_param}"

        # Add parameters
        params = []

        # Add sources and destinations (OSRM uses semicolons, not commas)
        if sources:
            sources_str = ';'.join(str(i) for i in sources)
            params.append(f"sources={sources_str}")

        if destinations:
            destinations_str = ';'.join(str(i) for i in destinations)
            params.append(f"destinations={destinations_str}")

        # Add annotations
        annotations = ','.join(self.config['annotations'])
        params.append(f"annotations={annotations}")

        if params:
            url += "?" + "&".join(params)

        # Validate URL length and log the actual URL for debugging
        if len(url) > 1500:  # Conservative limit
            raise OSRMError(f"Generated URL too long ({len(url)} chars): {url[:200]}...")

        print(f"🔍 Generated URL length: {len(url)} chars")
        print(f"🔍 Generated URL: {url}")
        return url

    def _call_chunked_api(self, url: str) -> Dict[str, Any]:
        """Call OSRM API for chunked request with enhanced error handling"""
        try:
            start_time = time.time()
            response = requests.get(url, timeout=self.timeout)
            call_duration = time.time() - start_time

            print(f"📡 OSRM API call: {len(url)} chars, {call_duration:.2f}s, status {response.status_code}")

            if response.status_code != 200:
                error_detail = response.text[:500] if len(response.text) > 500 else response.text
                raise OSRMError(f"OSRM API returned status {response.status_code}: {error_detail}")

            data = response.json()

            if data.get('code') != 'Ok':
                error_msg = data.get('message', 'Unknown error')
                raise OSRMError(f"OSRM API error: {error_msg}")

            return data

        except requests.exceptions.Timeout:
            raise OSRMError(f"OSRM API timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError:
            raise OSRMError(f"Cannot connect to OSRM server at {self.base_url}")
        except requests.exceptions.RequestException as e:
            raise OSRMError(f"OSRM API request failed: {e}")
        except json.JSONDecodeError:
            raise OSRMError("Invalid JSON response from OSRM API")

    def build_table_url(self, locations: List[Location],
                       sources: Optional[List[int]] = None,
                       destinations: Optional[List[int]] = None) -> str:
        """Build OSRM table API URL with conservative validation"""
        if len(locations) > self.max_locations:
            raise OSRMError(f"Too many locations ({len(locations)}). Max: {self.max_locations}")

        # Validate and convert locations to OSRM format (lon,lat)
        coord_strings = []
        for i, loc in enumerate(locations):
            # Validate coordinates
            if not (-90 <= loc.latitude <= 90):
                raise OSRMError(f"Invalid latitude at location {i}: {loc.latitude}")
            if not (-180 <= loc.longitude <= 180):
                raise OSRMError(f"Invalid longitude at location {i}: {loc.longitude}")

            # Check for NaN or None
            if loc.latitude is None or loc.longitude is None:
                raise OSRMError(f"Null coordinates at location {i}")

            try:
                # Use exactly 6 decimal places for consistency
                coord_string = f"{loc.longitude:.6f},{loc.latitude:.6f}"
                coord_strings.append(coord_string)
            except Exception as e:
                raise OSRMError(f"Error formatting coordinates at location {i}: {e}")

        # Join coordinates with semicolons
        coords_param = ';'.join(coord_strings)

        # Build base URL - DON'T URL encode the coordinates, OSRM expects them raw
        url = f"{self.base_url}{self.table_endpoint}{coords_param}"

        # Add parameters
        params = []

        if sources is not None:
            sources_str = ';'.join(str(i) for i in sources)
            params.append(f"sources={sources_str}")

        if destinations is not None:
            destinations_str = ';'.join(str(i) for i in destinations)
            params.append(f"destinations={destinations_str}")

        # Add annotations
        annotations = ','.join(self.config['annotations'])
        params.append(f"annotations={annotations}")

        if params:
            url += "?" + "&".join(params)

        # URL length check (generous for C++ parity)
        if len(url) > 3000:
            raise OSRMError(f"URL too long ({len(url)} chars). Reduce chunk size.")

        print(f"🔍 Final URL length: {len(url)} chars")
        print(f"🔍 Final URL: {url}")

        return url

    def call_table_api(self, locations: List[Location],
                      sources: Optional[List[int]] = None,
                      destinations: Optional[List[int]] = None) -> Dict[str, Any]:
        """Call OSRM table API exactly like C++ implementation"""
        url = self.build_table_url(locations, sources, destinations)

        logger.debug(f"Calling OSRM API: {url}")
        print(f"🌐 OSRM API Call (C++ parity):")
        print(f"   URL: {url[:100]}{'...' if len(url) > 100 else ''}")
        print(f"   Locations: {len(locations)}")
        if sources is None and destinations is None:
            print(f"   Mode: Full matrix (no sources/destinations)")
        else:
            print(f"   Mode: Partial matrix (sources: {len(sources) if sources else 0}, dest: {len(destinations) if destinations else 0})")

        try:
            start_time = time.time()
            response = requests.get(url, timeout=self.timeout)
            call_duration = time.time() - start_time

            print(f"   Response time: {call_duration:.2f}s")
            print(f"   Status code: {response.status_code}")

            logger.debug(f"OSRM API call completed in {call_duration:.2f}s")

            if response.status_code != 200:
                print(f"❌ OSRM API Error: Status {response.status_code}")
                print(f"   Response: {response.text[:300]}...")
                raise OSRMError(f"OSRM API returned status {response.status_code}: {response.text}")

            data = response.json()

            # Print response details
            print(f"   Response code: {data.get('code', 'Not specified')}")
            if data.get('code') != 'Ok':
                print(f"❌ OSRM API Error: {data.get('message', 'Unknown error')}")
                error_msg = data.get('message', 'Unknown error')
                raise OSRMError(f"OSRM API error: {error_msg}")

            # Print successful response summary
            print(f"✅ OSRM API Success:")
            if 'durations' in data:
                durations = data['durations']
                print(f"   Duration matrix: {len(durations)}x{len(durations[0])}")

            return data

        except requests.exceptions.Timeout:
            print(f"❌ OSRM API timeout after {self.timeout}s")
            raise OSRMError(f"OSRM API timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError:
            print(f"❌ Cannot connect to OSRM server at {self.base_url}")
            raise OSRMError(f"Cannot connect to OSRM server at {self.base_url}")
        except requests.exceptions.RequestException as e:
            print(f"❌ OSRM API request failed: {e}")
            raise OSRMError(f"OSRM API request failed: {e}")
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON response from OSRM")
            raise OSRMError("Invalid JSON response from OSRM API")

    def create_distance_matrix(self, locations: List[Location]) -> DistanceMatrix:
        """Create distance matrix with C++ parity logic"""
        if not locations:
            raise ValueError("At least one location is required")

        if len(locations) == 1:
            # Single location - create identity matrix
            return DistanceMatrix(
                locations=locations,
                durations=[[0.0]],
                distances=[[0.0]] if 'distance' in self.config['annotations'] else None
            )

        # Always use single call - C++ doesn't chunk for reasonable sizes
        print(f"🚀 Single API call for {len(locations)} locations (C++ parity mode)")
        return self._create_single_matrix(locations)

    def _create_single_matrix(self, locations: List[Location]) -> DistanceMatrix:
        """Create distance matrix with single API call"""
        response = self.call_table_api(locations)

        # Extract durations matrix
        durations = response['durations']

        # Convert from seconds to minutes if configured
        time_unit = CONFIG['business']['time_unit']
        print(f"🕒 Converting time units from seconds to {time_unit}")

        # Unreachable pairs from OSRM arrive as None (JSON null).
        # Use float('nan') so solver.py's nan_to_num replaces them with a
        # large sentinel (1e7) rather than 0.0 which would imply free travel.
        if time_unit == 'minutes':
            durations = [[cell / 60.0 if cell is not None else float('nan') for cell in row] for row in durations]
        elif time_unit == 'hours':
            durations = [[cell / 3600.0 if cell is not None else float('nan') for cell in row] for row in durations]
        else:
            durations = [[float(cell) if cell is not None else float('nan') for cell in row] for row in durations]

        # Extract distances if available
        distances = None
        if 'distances' in response:
            distances = response['distances']

        print(f"✅ Distance matrix created: {len(durations)}x{len(durations[0])} in {time_unit}")

        return DistanceMatrix(
            locations=locations,
            durations=durations,
            distances=distances
        )

    def _create_batched_matrix(self, locations: List[Location], chunk_size: int) -> DistanceMatrix:
        """Create distance matrix with conservative chunking"""
        n = len(locations)
        durations = [[0.0] * n for _ in range(n)]
        distances = [[0.0] * n for _ in range(n)] if 'distance' in self.config['annotations'] else None

        logger.info(f"Creating chunked distance matrix for {n} locations with chunk size {chunk_size}")
        print(f"🔄 C++ chunking:")
        print(f"   Total locations: {n}")
        print(f"   Chunk size: {chunk_size}")
        print(f"   Number of chunks: {math.ceil(n / chunk_size) ** 2}")

        chunk_count = 0
        successful_chunks = 0
        failed_chunks = 0
        total_chunks = math.ceil(n / chunk_size) ** 2

        for source_start in range(0, n, chunk_size):
            source_end = min(source_start + chunk_size, n)

            for dest_start in range(0, n, chunk_size):
                dest_end = min(dest_start + chunk_size, n)
                chunk_count += 1

                print(f"   Processing chunk {chunk_count}/{total_chunks}: sources[{source_start}:{source_end}] → dest[{dest_start}:{dest_end}]")

                try:
                    # Create chunk locations and mappings
                    chunk_locations = []
                    source_mapping = {}
                    dest_mapping = {}

                    # Add source locations
                    for idx, loc_idx in enumerate(range(source_start, source_end)):
                        chunk_locations.append(locations[loc_idx])
                        source_mapping[loc_idx] = idx

                    # Add destination locations (avoid duplicates)
                    for loc_idx in range(dest_start, dest_end):
                        if loc_idx not in source_mapping:
                            chunk_locations.append(locations[loc_idx])
                            dest_mapping[loc_idx] = len(chunk_locations) - 1
                        else:
                            dest_mapping[loc_idx] = source_mapping[loc_idx]

                    # Define sources and destinations indices for OSRM
                    sources = list(range(len(source_mapping)))
                    destinations = [dest_mapping[loc_idx] for loc_idx in range(dest_start, dest_end)]

                    # Build URL with sources/destinations parameters
                    url = self._build_chunked_url(chunk_locations, sources, destinations)

                    # Make API call (fail fast, no fallbacks)
                    response = self._call_chunked_api(url)

                    # Extract and convert results
                    batch_durations = response['durations']
                    batch_distances = response.get('distances')

                    # Convert time units
                    time_unit = CONFIG['business']['time_unit']
                    if time_unit == 'minutes':
                        batch_durations = [[cell / 60.0 if cell is not None else 0.0 for cell in row] for row in batch_durations]
                    elif time_unit == 'hours':
                        batch_durations = [[cell / 3600.0 if cell is not None else 0.0 for cell in row] for row in batch_durations]

                    # Fill the full matrix
                    for src_idx, global_src in enumerate(range(source_start, source_end)):
                        for dest_idx, global_dest in enumerate(range(dest_start, dest_end)):
                            durations[global_src][global_dest] = batch_durations[src_idx][dest_idx]
                            if distances and batch_distances:
                                distances[global_src][global_dest] = batch_distances[src_idx][dest_idx]

                    successful_chunks += 1
                    print(f"   ✅ Chunk {chunk_count} completed successfully")

                except Exception as e:
                    failed_chunks += 1
                    print(f"   ❌ Chunk {chunk_count} failed: {e}")
                    # Fail fast - re-raise the exception instead of using fallbacks
                    raise OSRMError(f"Chunk {chunk_count} failed, aborting: {e}")

        print(f"✅ C++ chunked matrix completed:")
        print(f"   Successful chunks: {successful_chunks}/{total_chunks}")
        if failed_chunks > 0:
            print(f"   Failed chunks: {failed_chunks}/{total_chunks} (operation aborted)")

        return DistanceMatrix(
            locations=locations,
            durations=durations,
            distances=distances
        )

    def get_route_matrix(self, sources: List[Location],
                        destinations: List[Location]) -> DistanceMatrix:
        """Get distance matrix between two sets of locations"""
        # Combine all locations
        all_locations = sources + destinations

        # Define source and destination indices
        source_indices = list(range(len(sources)))
        dest_indices = list(range(len(sources), len(all_locations)))

        response = self.call_table_api(all_locations, source_indices, dest_indices)

        # Extract and convert durations
        durations = response['durations']
        time_unit = CONFIG['business']['time_unit']
        if time_unit == 'minutes':
            durations = [[cell / 60.0 if cell is not None else 0.0 for cell in row] for row in durations]
        elif time_unit == 'hours':
            durations = [[cell / 3600.0 if cell is not None else 0.0 for cell in row] for row in durations]

        # Extract distances if available
        distances = None
        if 'distances' in response:
            distances = response['distances']

        return DistanceMatrix(
            locations=all_locations,
            durations=durations,
            distances=distances
        )


# Convenience functions
def calculate_matrix_for_problem(technicians: List, work_orders: List) -> DistanceMatrix:
    """Calculate distance matrix for a complete optimization problem"""
    locations = (
        [tech.start_location for tech in technicians] +
        [order.location for order in work_orders]
    )

    cache_key = tuple((loc.latitude, loc.longitude) for loc in locations)
    if cache_key in _matrix_cache:
        logger.debug("OSRM matrix cache hit (%d locations)", len(locations))
        return _matrix_cache[cache_key]

    client = OSRMClient()
    result = client.create_distance_matrix(locations)
    _matrix_cache[cache_key] = result
    return result


def validate_osrm_connection() -> bool:
    """Validate OSRM server connection"""
    client = OSRMClient()
    return client.health_check()


def get_travel_time(from_location: Location, to_location: Location) -> float:
    """Get travel time between two locations"""
    client = OSRMClient()
    matrix = client.create_distance_matrix([from_location, to_location])
    return matrix.get_duration(0, 1)


# Example usage and testing functions
def test_osrm_integration():
    """Test OSRM integration with sample PJ data"""
    # Sample PJ locations with exactly 5 decimal places
    locations = [
        Location(3.10837, 101.58150, "Section 14, PJ"),
        Location(3.08650, 101.59339, "USJ 1"),
        Location(3.11419, 101.62060, "Section 17, PJ")
    ]

    try:
        client = OSRMClient()

        # Test health check
        if not client.health_check():
            print("❌ OSRM server not accessible")
            return False

        print("✅ OSRM server accessible")

        # Test simple 2-location matrix first to validate format
        simple_locations = locations[:2]
        print(f"\n🧪 Testing simple 2-location matrix first:")
        simple_matrix = client.create_distance_matrix(simple_locations)

        print(f"✅ Simple matrix worked! Duration matrix (minutes):")
        for i, row in enumerate(simple_matrix.durations):
            print(f"  {i}: {[round(x, 1) for x in row]}")

        # Now test full 3-location matrix
        print(f"\n🧪 Testing full 3-location matrix:")
        matrix = client.create_distance_matrix(locations)

        print(f"✅ Distance matrix calculated for {len(locations)} locations")
        print("Duration matrix (minutes):")
        for i, row in enumerate(matrix.durations):
            print(f"  {i}: {[round(x, 1) for x in row]}")

        return True

    except OSRMError as e:
        print(f"❌ OSRM Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    # Run tests when module is executed directly
    print("Testing OSRM integration...")
    test_osrm_integration()