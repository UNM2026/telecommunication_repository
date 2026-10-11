import csv
import geopandas as gpd
import pandas as pd
import requests

# --- PART 1: Fetch data from the API and save to CSV ---
API_KEY = "bbm_live_1qkwcDSAM1ROSiuuWbWiN3OrokOksQrhIjori_8LrqU"

# Representative coordinates for your target towns
target_towns = [
    {"name": "Taos", "lat": 36.4072, "lng": -105.5734},
    {"name": "Chama", "lat": 36.8973, "lng": -106.5778},
    {"name": "Bloomfield", "lat": 36.7084, "lng": -107.9906},
    {"name": "Cuba", "lat": 36.0247, "lng": -106.9453},
]

csv_filename = r"C:\Users\zack\Documents\ECE220\Project\broadband_providers.csv"

print("Starting multi-town API data pull...")
with open(csv_filename, "w", newline="", encoding="utf-8") as f:
  writer = csv.writer(f)
  writer.writerow(
      [
          "town_queried",
          "long",
          "lat",
          "provider",
          "technology",
          "h3",
          "up",
          "down",
      ]
  )

  for town in target_towns:
    town_name = town["name"]
    lat = town["lat"]
    lng = town["lng"]

    print(f"Fetching data for {town_name} (lat: {lat}, lng: {lng})...")
    url = f"https://broadbandmap.com/api/v1/location/internet?lat={lat}&lng={lng}"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    try:
      response = requests.get(url, headers=headers)

      if response.status_code == 200:
        data = response.json()
        lat_val = data.get("lat")
        lng_val = data.get("lng")
        h3_val = data.get("h3_hex")

        providers = data.get("providers", [])
        print(f" -> Found {len(providers)} providers for {town_name}.")

        for provider in providers:
          provider_name = provider.get("name")
          technology = provider.get("technology")
          max_down = provider.get("max_download_mbps")
          max_up = provider.get("max_upload_mbps")

          writer.writerow(
              [
                  town_name,
                  lng_val,
                  lat_val,
                  provider_name,
                  technology,
                  h3_val,
                  max_up,
                  max_down,
              ]
          )
      else:
        print(
            f" -> Error {response.status_code} for {town_name}:"
            f" {response.text}"
        )

    except Exception as e:
      print(f" -> An error occurred while fetching {town_name}: {e}")

print(f"\nAPI data pulled and saved to {csv_filename}")


# --- PART 2: Merge with Official US Census Places (with a buffer) ---
print("\nDownloading official US Census TIGER/Line Places for New Mexico...")
url_census = (
    "https://www2.census.gov/geo/tiger/TIGER2018/PLACE/tl_2018_35_place.zip"
)
gdf_places = gpd.read_file(url_census)

# Ensure standard WGS84 coordinate reference system (EPSG:4326)
if gdf_places.crs is None:
  gdf_places = gdf_places.set_crs("EPSG:4326")
elif gdf_places.crs != "EPSG:4326":
  gdf_places = gdf_places.to_crs("EPSG:4326")

# Define target towns (including misspellings from notes)
target_variants = [
    "Taos",
    "Toas",
    "Bloomfield",
    "Bloomsfield",
    "Chama",
    "Chana",
    "Cuba",
]
pattern = "|".join(target_variants)

# Filter the Census places layer to target towns
gdf_geog = gdf_places[
    gdf_places["NAME"].astype(str).str.contains(pattern, case=False, na=False)
].copy()

# Project to a metric CRS temporarily, add a 500-meter buffer, then convert back
# This prevents points right on the edge from being discarded by spatial joins.
gdf_geog_projected = gdf_geog.to_crs(epsg=3857)  # Web Mercator (meters)
gdf_geog_projected["geometry"] = gdf_geog_projected["geometry"].buffer(500)
gdf_geog = gdf_geog_projected.to_crs(epsg=4326)

print("\nTown polygons successfully buffered and found:")
print(gdf_geog[["NAME", "GEOID"]])

# Load the broadband providers CSV we just generated
print("\nReading Broadband Providers CSV data for spatial join...")
df_broadband = pd.read_csv(csv_filename)

# Create GeoDataFrame using long/lat points
gdf_broadband_points = gpd.GeoDataFrame(
    df_broadband,
    geometry=gpd.points_from_xy(df_broadband["long"], df_broadband["lat"]),
    crs="EPSG:4326",
)

print("Performing spatial join with buffered town boundaries...")
gdf_joined = gpd.sjoin(
    gdf_broadband_points, gdf_geog, how="inner", predicate="within"
)

# Clean up geometry column for final output table
df_final = pd.DataFrame(
    gdf_joined.drop(columns=["geometry"], errors="ignore")
)

found_towns = (
    df_final["NAME"].unique() if not df_final.empty else []
)
print("\nTowns successfully matched in final merged dataset:", found_towns)
print(f"Total matching provider-location rows merged: {len(df_final)}")

# Save the fully merged dataset containing the provider names
output_final_path = (
    r"C:\Users\zack\Documents\ECE220\Project\broadband_merged_with_census_places.csv"
)
df_final.to_csv(output_final_path, index=False)
print(f"Success! Fully merged dataset saved to {output_final_path}")