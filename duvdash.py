from IT8951.display import AutoEPDDisplay
from IT8951 import constants
from PIL import Image, ImageFont, ImageDraw

import datetime
import os.path
import sys
import requests
from collections import defaultdict

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.events.readonly"]
DIR = os.path.dirname(__file__)

TODOIST_API_KEY = os.getenv("TODOIST_API_KEY")

def get_credentials() -> Credentials:
    creds = None
    creds_filename = os.path.join(DIR, 'token.json')
    if os.path.exists(creds_filename):
        creds = Credentials.from_authorized_user_file(creds_filename, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(creds_filename, "w") as token:
                token.write(creds.to_json())
        else:
            print("Need freshly authorised credentials!", creds.valid)
            sys.exit(1)

    return creds

def get_upcoming_events(service, max_results: int = 30):
    now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return events_result.get("items", [])

def get_duvland_tasks():
    if not TODOIST_API_KEY:
        print("Missing Todoist API key. Please set TODOIST_API_KEY environment variable.")
        sys.exit(1)

    url = "https://api.todoist.com/rest/v2/tasks"
    headers = {
        "Authorization": f"Bearer {TODOIST_API_KEY}"
    }
    params = {
        "project_id": "2204654002"
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print(f"Failed to fetch tasks: {response.status_code}")
        return []

    return response.json()

def group_items_by_date(events, tasks):
    grouped = defaultdict(lambda: {"events": [], "tasks": []})

    for event in events:
        start_date = event['start'].get('dateTime', event['start'].get('date')).split("T")[0]
        grouped[start_date]["events"].append(event)

    for task in tasks:
        due = task.get('due')
        if due:
            due_date = due.get('date')
            if due_date:
                grouped[due_date]["tasks"].append(task)

    return dict(grouped)

def initialize_display() -> AutoEPDDisplay:
    display = AutoEPDDisplay(vcom=-1.23, mirror=True)
    display.clear()
    return display

weather_code_mapping = {
    0: "Clear Sky",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light Rain Showers",
    53: "Rain Showers",
    55: "Heavy Rain Showers",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    71: "Light Snow Showers",
    73: "Snow Showers",
    75: "Heavy Snow Showers",
    80: "Light Rain Showers",
    81: "Rain Showers",
    82: "Heavy Rain Showers",
    85: "Light Snow",
    86: "Heavy Snow",
    95: "Thunderstorm",
    96: "Thunderstorm with Rain",
    99: "Thunderstorm with Heavy Rain",
}


# Fetch Weather Data from Open-Meteo
def fetch_weather_forecast():
    # Get weather forecast for Almada, Portugal using Open-Meteo API
    latitude, longitude = 38.6762, -9.3986  # Coordinates for Almada, Portugal
    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&daily=weathercode&timezone=Europe/Lisbon"
    response = requests.get(weather_url)

    if response.status_code != 200:
        print(f"Failed to fetch weather: {response.status_code}")
        return {}

    weather_data = response.json()
    weather_forecast = {}
    daily_forecasts = weather_data.get("daily", {})

    for i, date in enumerate(daily_forecasts.get("time", [])):
        weather_code = daily_forecasts.get("weathercode", [])[i]
        weather_forecast[date] = weather_code_mapping[weather_code]

    return weather_forecast

# Fetch an Inspirational Quote using ZenQuotes
def fetch_inspirational_quote():
    # Fetch an inspirational quote about teamwork & family from ZenQuotes
    quote_url = "https://zenquotes.io/api/random"
    response = requests.get(quote_url)

    if response.status_code != 200:
        print(f"Failed to fetch quote: {response.status_code}")
        return "Together, we achieve more."

    quote_data = response.json()
    quote = quote_data[0].get("q", "Together, we achieve more.")
    author = quote_data[0].get("a", "Anon")
    return "\"" + quote + "\" - " + author

def render_weekly_planner(display: AutoEPDDisplay, grouped_items: dict, weather_forecast: dict, inspirational_quote: str):
    # Prepare the image to draw on
    Himage = Image.new('1', (display.width, display.height), 255)  # 255 = white
    draw = ImageDraw.Draw(Himage)

    # Load fonts
    font_bold = ImageFont.truetype(os.path.join(DIR, "Lato-Bold.ttf"), 40)  # Increased font size
    font_bold_smaller = ImageFont.truetype(os.path.join(DIR, "Lato-Bold.ttf"), 28)  # Increased font size
    font_regular = ImageFont.truetype(os.path.join(DIR, "Lato-Regular.ttf"), 28)  # Better readability

    # Layout variables
    margin = 10
    box_width = (display.width - margin * 4) // 3  # Three columns
    box_height_with_events = (display.height - margin * 6) // 4  # Four rows for 6 day boxes + Todos + Margin

    # Define the starting positions
    y_pos = margin * 2 + 60  # Header height included

    # Get the current week number
    current_week_number = datetime.date.today().isocalendar()[1]

    # Get today's date
    today = datetime.datetime.now()

    # Find the most recent Monday
    monday = today - datetime.timedelta(days=today.weekday())

    # Generate the dates for the current week starting from Monday
    week_dates = [(monday + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
    weekend_dates = [(monday + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5,7)]

    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Weekend"]

    # Draw header for the planner
    draw.text((margin, margin), f'WEEKLY PLANNER - Week {current_week_number}', font=font_bold, fill=0)
    draw.text((display.width - 300, margin), f'\nlast refreshed: {today.strftime("%H:%M")}', font=font_regular, fill=0)

    # Render each day of the week in a separate box
    for idx, day in enumerate(days_of_week):
        # Calculate the position of each box
        box_x = margin + (idx % 3) * (box_width + margin)
        box_y = y_pos + (idx // 3) * (box_height_with_events + margin)

        label_idx = -2
        if datetime.date.today().day == 1:
            label_idx = -5

        # Handle weekend separately
        if day == "Weekend":
            day_dates = weekend_dates
            label = f"Weekend ({weekend_dates[0][label_idx:]} - {weekend_dates[1][-2:]})"
        else:
            day_dates = [week_dates[idx]]
            label = f"{day} ({day_dates[0][label_idx:]})"

        # Highlight today's box with a thicker border
        is_today = day == datetime.date.today().strftime("%A") or (day == "Weekend" and datetime.date.today().weekday() > 4)
        border_width = 6 if is_today else 2

        # Draw the box for the day with rounded corners
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_width, box_y + box_height_with_events],
            radius=15,
            outline=0,
            width=border_width
        )

        # Add weather information to the day's header
        weather = weather_forecast.get(day_dates[0], "")

        # Write the day title and weather
        draw.text((box_x + 10, box_y + 10), f"{label}", font=font_bold, fill=0)
        draw.text((box_x + 10, box_y + 10), f"\n\n{weather}", font=font_bold_smaller, fill=0)

        # Render events for the date(s)
        current_y = box_y + 110  # Increased gap for larger text
        for day_date in day_dates:
            events = grouped_items.get(day_date, {}).get("events", [])
            for event in events:
                start_time = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'No Title')

                # Highlight all-day events differently
                if 'T' not in start_time:  # No specific time, hence all-day event
                    draw.text((box_x + 10, current_y), f"{summary}", font=font_bold, fill=0)
                else:
                    start_time = start_time.split("T")[1].split("+")[0]  # Extract time from dateTime
                    draw.text((box_x + 10, current_y), f"{start_time} - {summary}", font=font_regular, fill=0)

                current_y += 50  # Larger gap for larger text

                # Ensure not to overflow the box
                if current_y > box_y + box_height_with_events - 50:
                    draw.text((box_x + 10, current_y), "...", font=font_regular, fill=0)
                    break

    # Render "Todos This Week" box below all day boxes
    todos_x = margin
    todos_y = y_pos + 2 * (box_height_with_events + margin)  # Positioned below all the day boxes
    draw.rounded_rectangle(
        [todos_x, todos_y, todos_x + display.width - margin * 2, todos_y + box_height_with_events / 2],
        radius=15,
        outline=0,
        width=2
    )
    draw.text((todos_x + 10, todos_y + 10), "Todos", font=font_bold, fill=0)

    # Render tasks inside the "Todos This Week" box
    current_y = todos_y + 70
    for day_date in week_dates + weekend_dates:
        tasks = grouped_items.get(day_date, {}).get("tasks", [])
        for task in tasks:
            content = task.get('content', 'No Content')
            draw.text((todos_x + 10, current_y), f"{content}", font=font_regular, fill=0)
            current_y += 50

            # Ensure not to overflow the box
            if current_y > todos_y + box_height_with_events - 50:
                draw.text((todos_x + 10, current_y), "...", font=font_regular, fill=0)
                break

    # Render the inspirational quote at the bottom of the screen
    quote_y = todos_y + box_height_with_events + margin
    draw.text((margin, quote_y), inspirational_quote, font=font_regular, fill=0)

    Himage.save("weekly_planner_preview.bmp")

    # Display the image on the screen
    display.frame_buf.paste(Himage)
    display.draw_full(constants.DisplayModes.GC16)

# Main function
def main():
    # Fetch the weather and quote
    weather_forecast = fetch_weather_forecast()
    # weather_forecast = {}
    inspirational_quote = fetch_inspirational_quote()

    # Initialize the Google Calendar and Todoist services
    creds = get_credentials()

    try:
        service = build("calendar", "v3", credentials=creds)
        events = get_upcoming_events(service)
        tasks = get_duvland_tasks()

        # Group events and tasks by date
        grouped_items = group_items_by_date(events, tasks)

        # Initialize display
        display = initialize_display()

        # Render weekly planner
        render_weekly_planner(display, grouped_items, weather_forecast, inspirational_quote)

    except HttpError as error:
        print(f"An error occurred: {error}")

if __name__ == "__main__":
    main()
