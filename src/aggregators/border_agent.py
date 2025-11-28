import httpx
import asyncio

class BorderWaitAgent:
    # Official CBP (Customs and Border Protection) JSON Feed
    DATA_URL = "https://bwt.cbp.gov/api/bwt/current"

    async def get_wait_time(self, crossing_query: str) -> dict:
        """
        Searches for a border crossing by name and returns live wait times.
        """
        crossing_query = crossing_query.lower()
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.DATA_URL, timeout=10.0)
                resp.raise_for_status()
                data = resp.json()

            found_port = None
            
            # Search for the requested port in the dataset
            for port in data:
                port_name = port.get('portName', '').lower()
                crossing_name = port.get('crossingName', '').lower()
                
                if crossing_query in port_name or crossing_query in crossing_name:
                    found_port = port
                    break
            
            if not found_port:
                return {
                    "error": "Crossing not found", 
                    "query": crossing_query,
                    "available_examples": ["San Ysidro", "Otay Mesa", "El Paso"]
                }

            # Extract Passenger Vehicle data
            passenger_data = found_port.get('passenger', {}).get('standard_lanes', {})
            wait_minutes = passenger_data.get('delay_minutes')
            
            # Handle closed lanes or missing data
            if wait_minutes is None:
                status = "Closed/No Data"
                wait_time = 0
            else:
                status = "Open"
                wait_time = int(wait_minutes)

            # Construct the response
            return {
                "crossing": found_port.get('portName'),
                "specific_lane": found_port.get('crossingName'),
                "wait_time_minutes": wait_time,
                "status": found_port.get('portStatus', status),
                "last_updated": found_port.get('date') + " " + found_port.get('time'),
                "source": "Official CBP API",
                "verified": True
            }

        except Exception as e:
            print(f"❌ Error fetching border data: {e}")
            return {
                "error": "External API Error", 
                "details": str(e)
            }