# SnowPlanner
SnowPlanner is a visual tool to plan deliveries in the game SnowRunner. Other tools (and SnowRunner itself) let you see one objective at a time, SnowPlanner lets you see all in and area or even region. If you've ever been frustrated by missing opportunities to combine trips, this could be just the tool for you.

Note that the default view with no objectives marked as complete can be pretty busy. There are buttons to hide categories at the top, and objectives and limited sources can be marked as complete, which by default hides them from the objectives tree and the map view. Specific objectives or cargo items can be highlighted in the map view.

Lines are drawn from trucks, trailers etc to their drop-off location. Objectives that are blocked because prerequisite objectives have not been marked as complete are displayed in darker colors on the map and in dark red in the objectives tree. Clicking a listed blocking objective in the tree navigates to that objective.

This is a work in progress. I made this to help my own play-style. It has evolved from individual scripts and text data files to a web application with a SQLite database. Some parts are still pretty rough. But it is functional enough for me to complete multiple regions with it. I'm open to suggestions and code contributions, but bear in mind that it doesn't yet have everything I want to put in it. I'm putting it on GitHub so that like-minded individuals can benefit.

# Installation instructions

Because this project does not have standalone releases, you must install or run it directly from the source code. Ensure you have [Python 3.10+](https://www.python.org/) installed before proceeding.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/cdbassett/snowplanner.git
   cd snowplanner
   ```

2. **Create and activate a virtual environment:**
   * **macOS/Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   * **Windows:**
     ```bash
     python -m venv .venv
     .venv\Scripts\activate
     ```

3. **Install the required dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Run the project:**
   ```bash
   python snowplanner_app.py
   ```

# Screenshots
## Area
![Area view](<screenshots/SnowPlanner area screenshot.png>)
## Region
![Region view](<screenshots/SnowPlanner region screenshot.png>)
