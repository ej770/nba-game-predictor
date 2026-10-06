"""Power BI report definition (report.json, PBIR-legacy format) for the NBA Game Predictor,
generated in Python so the whole report is code. Used by the NBA_Report_Builder notebook."""
import json

W, H = 1280, 720
GREY = "#605E5C"


def lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = f"{v}L"
    elif isinstance(v, float):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


class Q:
    """Builds the prototypeQuery and projections of one visual."""

    def __init__(self):
        self.sources, self.select, self.proj, self.order, self.names = {}, [], {}, [], {}

    def _alias(self, table):
        if table not in self.sources:
            self.sources[table] = f"t{len(self.sources)}"
        return self.sources[table]

    def _ref(self, table, prop, kind, fn=None):
        src = {"Expression": {"SourceRef": {"Source": self._alias(table)}}, "Property": prop}
        if kind == "measure":
            return {"Measure": src}, f"{table}.{prop}"
        if kind == "avg":
            return {"Aggregation": {"Expression": {"Column": src}, "Function": 1}}, f"Avg({table}.{prop})"
        if kind == "sum":
            return {"Aggregation": {"Expression": {"Column": src}, "Function": 0}}, f"Sum({table}.{prop})"
        return {"Column": src}, f"{table}.{prop}"

    def add(self, role, table, prop, kind="column", name=None, sort=None):
        expr, ref = self._ref(table, prop, kind)
        if ref not in [s["Name"] for s in self.select]:
            self.select.append({**expr, "Name": ref, "NativeReferenceName": name or prop})
        item = {"queryRef": ref}
        if role == "Category" and kind == "column":
            item["active"] = True
        self.proj.setdefault(role, []).append(item)
        if name:
            self.names[ref] = name
        if sort:
            self.order.append({"Direction": 1 if sort == "asc" else 2, "Expression": expr})
        return self

    def visual(self, vtype, objects=None, title=None, vc_extra=None):
        query = {"Version": 2, "From": [{"Name": a, "Entity": t, "Type": 0} for t, a in self.sources.items()],
                 "Select": self.select}
        if self.order:
            query["OrderBy"] = self.order
        sv = {"visualType": vtype, "projections": self.proj, "prototypeQuery": query,
              "drillFilterOtherVisuals": True, "hasDefaultSort": not self.order}
        if self.names:
            sv["columnProperties"] = {ref: {"displayName": n} for ref, n in self.names.items()}
        objects = {**(objects or {}), "total": [{"properties": {"totals": lit(False)}}]} if vtype == "tableEx" else objects
        if objects:
            sv["objects"] = objects
        vco = {"title": [{"properties": {"show": lit(bool(title)), **({"text": lit(title)} if title else {})}}]}
        if vc_extra:
            vco.update(vc_extra)
        sv["vcObjects"] = vco
        return sv


def text_visual(lines):
    paragraphs = []
    for text, size, bold, color in lines:
        style = {"fontSize": f"{size}pt"}
        if bold:
            style["fontWeight"] = "bold"
        if color:
            style["color"] = color
        paragraphs.append({"textRuns": [{"value": text, "textStyle": style}]})
    return {"visualType": "textbox", "drillFilterOtherVisuals": True,
            "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]}}


def column_filter(table, column, values, name):
    return {"name": name, "expression": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}},
            "filter": {"Version": 2, "From": [{"Name": "f", "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "f"}}, "Property": column}}],
                           "Values": [[{"Literal": {"Value": "'" + v + "'"}}] for v in values]}}}]},
            "type": "Categorical", "howCreated": 1}


def measure_filter(table, measure, value, name):
    ref = {"Measure": {"Expression": {"SourceRef": {"Source": "f"}}, "Property": measure}}
    return {"name": name, "expression": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": measure}},
            "filter": {"Version": 2, "From": [{"Name": "f", "Entity": table, "Type": 0}],
                       "Where": [{"Condition": {"Comparison": {"ComparisonKind": 0, "Left": ref,
                                                               "Right": {"Literal": {"Value": f"{value}L"}}}}}]},
            "type": "Advanced", "howCreated": 1}


class Page:
    def __init__(self, name, display, ordinal, filters=None):
        self.name, self.display, self.ordinal, self.filters = name, display, ordinal, filters or []
        self.visuals = []

    def add(self, vid, x, y, w, h, single_visual, filters=None):
        z = 1000 * (len(self.visuals) + 1)
        cfg = {"name": f"p{self.ordinal}{vid}", "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h,
                                                               "tabOrder": z}}],
               "singleVisual": single_visual}
        self.visuals.append({"x": x, "y": y, "z": z, "width": w, "height": h,
                             "config": json.dumps(cfg), "filters": json.dumps(filters or [])})

    def section(self):
        return {"name": self.name, "displayName": self.display, "ordinal": self.ordinal,
                "displayOption": 1, "width": W, "height": H, "config": "{}",
                "filters": json.dumps(self.filters), "visualContainers": self.visuals}


def card(table, measure, label):
    return Q().add("Values", table, measure, "measure", name=label).visual(
        "card", objects={"labels": [{"properties": {"fontSize": lit(24.0)}}],
                         "categoryLabels": [{"properties": {"show": lit(True), "fontSize": lit(10.0)}}]})


def slicer(table, column, title, force=False):
    return Q().add("Values", table, column).visual(
        "slicer", title=title,
        objects={"data": [{"properties": {"mode": lit("Dropdown")}}],
                 "selection": [{"properties": {"singleSelect": lit(True), "strictSingleSelect": lit(force)}}],
                 "header": [{"properties": {"show": lit(False)}}]})


def build() -> dict:
    test_only = [column_filter("games", "split", ["Test seasons"], "TestSeasons")]
    all_seasons = [column_filter("games", "split", ["Earlier seasons", "Test seasons"], "AllSeasons")]  # hides the blank member

    # ---- Page 1: pre-game picks -------------------------------------------------------------
    # ---- Page 0: the 2026-27 season, refreshed daily by NBA_Upcoming_Picks ----------------------
    p0 = Page("ReportSection0season", "2026-27 picks", 0)
    p0.add("title", 24, 12, 1232, 64, text_visual([
        ("2026-27 picks", 20, True, None),
        ("Every game of the new season, picked before tip-off by the registered model and graded once "
         "it's played. Refreshed daily from ESPN's schedule.", 11, False, GREY)]))
    for i, (m, label) in enumerate([("Record", "Picks right so far"), ("Upcoming Games", "Games picked, next 2 weeks"),
                                    ("Last Updated", "Last updated")]):
        p0.add(f"card{i}", 24 + i * 316, 88, 300, 96, card("season_picks", m, label))
    played = lambda stage: [column_filter("season_picks", "stage", [stage], f"Stage{stage}")]
    p0.add("upcoming", 24, 200, 610, 500, Q()
           .add("Values", "season_picks", "game_date", sort="asc", name="Date")
           .add("Values", "season_picks", "away", name="Away")
           .add("Values", "season_picks", "home", name="Home")
           .add("Values", "season_picks", "model_pick", name="Our pick")
           .add("Values", "season_picks", "model_confidence", "sum", name="Confidence")
           .visual("tableEx", title="Upcoming games"), filters=played("Upcoming"))
    p0.add("results", 646, 200, 610, 500, Q()
           .add("Values", "season_picks", "game_date", sort="desc", name="Date")
           .add("Values", "season_picks", "final_score", name="Final score")
           .add("Values", "season_picks", "model_pick", name="Our pick")
           .add("Values", "season_picks", "model_confidence", "sum", name="Confidence")
           .add("Values", "season_picks", "model_correct", "sum", name="Right? (1 = yes)")
           .visual("tableEx", title="Results so far"), filters=played("Played"))

    p1 = Page("ReportSection1pregame", "Pre-game picks", 1, filters=test_only)
    p1.add("title", 24, 12, 1232, 64, text_visual([
        ("NBA Game Predictor: pre-game picks", 20, True, None),
        ("Graded on 2022-23 to 2025-26: 4,920 games the model never saw while it was built. "
         "Each season is predicted by a model trained only on earlier seasons.", 11, False, GREY)]))
    cards = [("Model Accuracy", "Our model (all games)"),
             ("Model Accuracy With Lines", "Our model (games with betting lines)"),
             ("Market Accuracy", "Las Vegas favourite"),
             ("Elo Accuracy", "Elo ratings alone"),
             ("Home Win Rate", "Always pick the home team")]
    for i, (m, label) in enumerate(cards):
        p1.add(f"card{i}", 24 + i * 248, 88, 236, 104, card("games", m, label))
    p1.add("bySeason", 24, 206, 760, 494, Q()
           .add("Category", "season_accuracy", "season_label", sort="asc")
           .add("Y", "season_accuracy", "model_accuracy", "avg", name="Our model")
           .add("Y", "season_accuracy", "vegas_accuracy", "avg", name="Las Vegas favourite")
           .add("Y", "season_accuracy", "elo_accuracy", "avg", name="Elo alone")
           .add("Y", "season_accuracy", "home_team_accuracy", "avg", name="Home team")
           .visual("lineChart", title="Share of games picked correctly, by season",
                   objects={"valueAxis": [{"properties": {"start": lit(0.5), "end": lit(0.75)}}],
                            "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]}))
    p1.add("confidence", 800, 206, 456, 236, Q()
           .add("Category", "confidence", "min_confidence", sort="asc", name="Model is at least this sure")
           .add("Y", "confidence", "accuracy", "avg", name="Picks that were right")
           .visual("clusteredColumnChart", title="The surer the model, the more often it's right",
                   objects={"valueAxis": [{"properties": {"start": lit(0.5), "end": lit(1.0)}}],
                            "labels": [{"properties": {"show": lit(True)}}]}))
    p1.add("leakage", 800, 456, 456, 244, Q()
           .add("Values", "leakage_demo", "model", name="What the model is given")
           .add("Values", "leakage_demo", "test_accuracy", "sum", name="Accuracy")
           .add("Values", "leakage_demo", "known_before_tipoff", name="Known before tip-off?")
           .visual("tableEx", title="The 99% trap: only the honest model can be used before tip-off"))

    # ---- Page 2: live win probability ---------------------------------------------------------
    p2 = Page("ReportSection2live", "Live win probability", 2)
    p2.add("title", 24, 12, 1232, 64, text_visual([
        ("Live win probability", 20, True, None),
        ("Every 15 seconds of every test-season game: the home team's chance to win from the score, "
         "the clock and the pre-game view. Pick a game below.", 11, False, GREY)]))
    p2.add("byMinute", 24, 88, 820, 320, Q()
           .add("Category", "live_by_minute", "minute", sort="asc", name="Minutes played")
           .add("Y", "live_by_minute", "accuracy", "avg", name="Score, clock and pre-game view")
           .add("Y", "live_by_minute", "accuracy_score_only", "avg", name="Score and clock only")
           .visual("lineChart", title="Share of games the leading side wins, by minutes played",
                   objects={"valueAxis": [{"properties": {"start": lit(0.5), "end": lit(1.0)}}],
                            "legend": [{"properties": {"show": lit(True), "position": lit("Top")}}]}))
    p2.add("checkpoints", 860, 88, 396, 320, Q()
           .add("Values", "live_checkpoints", "moment", name="Moment")
           .add("Values", "live_checkpoints", "accuracy", "sum", name="Picks right")
           .add("Values", "live_checkpoints", "seconds_played", "sum", sort="asc", name="Seconds played")
           .visual("tableEx", title="How often the live model is right"))
    team_filter = [measure_filter("games", "Selected Team Filter", 1, "TeamFilter")]
    p2.add("season", 24, 424, 180, 64, slicer("games", "season_label", "Season"), filters=test_only)
    p2.add("team", 212, 424, 180, 64, slicer("teams", "team", "Team"))
    p2.add("game", 400, 424, 444, 64, slicer("games", "game_label", "Game", force=True), filters=test_only + team_filter)
    p2.add("wpChart", 24, 500, 820, 200, Q()
           .add("Category", "live_win_probability", "minutes_played", sort="asc", name="Minutes played")
           .add("Y", "live_win_probability", "Home Win Probability", "measure", name="Home team's chance to win")
           .visual("lineChart", title="Home team's win probability",
                   objects={"valueAxis": [{"properties": {"start": lit(0.0), "end": lit(1.0)}}]}))
    p2.add("gameCard", 860, 424, 396, 276, Q()
           .add("Values", "games", "final_score", name="Final score")
           .add("Values", "games", "model_pick", name="Pre-game pick")
           .add("Values", "games", "model_confidence", "sum", name="Pre-game confidence")
           .add("Values", "games", "vegas_pick", name="Las Vegas favourite")
           .visual("multiRowCard", title="The game"))

    # ---- Page 3: games and teams ---------------------------------------------------------------
    p3 = Page("ReportSection3games", "Games and teams", 3)
    p3.add("title", 24, 12, 1232, 64, text_visual([
        ("Every pick since 2010-11", 20, True, None),
        ("Each game's pre-game probability from our model, Elo and the betting market. "
         "Filter by season and team.", 11, False, GREY)]))
    p3.add("season", 24, 88, 180, 64, slicer("games", "season_label", "Season"), filters=all_seasons)
    p3.add("team", 212, 88, 180, 64, slicer("teams", "team", "Team"))
    p3.add("acc", 400, 88, 220, 64, card("games", "Team Model Accuracy", "Our model's accuracy"))
    p3.add("acc2", 628, 88, 220, 64, card("games", "Team Games", "Games"))
    p3.add("games", 24, 168, 824, 532, Q()
           .add("Values", "games", "game_date", sort="desc", name="Date")
           .add("Values", "games", "final_score", name="Final score")
           .add("Values", "games", "model_pick", name="Our pick")
           .add("Values", "games", "model_confidence", "sum", name="Confidence")
           .add("Values", "games", "model_correct", "sum", name="Right? (1 = yes)")
           .add("Values", "games", "vegas_pick", name="Vegas pick")
           .visual("tableEx", title="Games"), filters=team_filter)
    p3.add("elo", 864, 88, 392, 612, Q()
           .add("Category", "teams", "team_name", name="Team")
           .add("Y", "teams", "elo_start_2026_27", "sum", sort="desc", name="Elo rating")
           .visual("clusteredBarChart", title="Team strength going into 2026-27 (Elo)",
                   objects={"labels": [{"properties": {"show": lit(True)}}]}))

    config = {"version": "5.43", "themeCollection": {}, "activeSectionIndex": 0,
              "defaultDrillFilterOtherVisuals": True,
              "settings": {"useNewFilterPaneExperience": True, "allowChangeFilterTypes": True,
                           "useStylableVisualContainerHeader": True}}
    return {"config": json.dumps(config), "layoutOptimization": 0,
            "sections": [p.section() for p in (p0, p1, p2, p3)]}


if __name__ == "__main__":
    report = build()
    print(len(json.dumps(report)), "bytes,", sum(len(s["visualContainers"]) for s in report["sections"]), "visuals")
