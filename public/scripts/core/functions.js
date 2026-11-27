// Age rating labels, keyed by the values the API uses (GamesESRB in routes/games/schemas.py).
const AGE_RATING_LABELS = {
  rp: "Rating Pending", ec: "Early Childhood", e: "Everyone", e10: "Everyone 10+", t: "Teen",
  m: "Mature 17+", ao: "Adults Only 18+",
  three: "PEGI 3", seven: "PEGI 7", twelve: "PEGI 12", sixteen: "PEGI 16", eighteen: "PEGI 18",
  cero_a: "CERO A (All Ages)", cero_b: "CERO B (Ages 12+)", cero_c: "CERO C (Ages 15+)",
  cero_d: "CERO D (Ages 17+)", cero_z: "CERO Z (Ages 18+)",
  usk_0: "USK 0 (All Ages)", usk_6: "USK 6 (Ages 6+)", usk_12: "USK 12 (Ages 12+)",
  usk_16: "USK 16 (Ages 16+)", usk_18: "USK 18 (Ages 18+)",
  grac_all: "GRAC All", grac_twelve: "GRAC 12 (Ages 12+)", grac_fifteen: "GRAC 15 (Ages 15+)",
  grac_eighteen: "GRAC 18 (Ages 18+)", grac_testing: "GRAC Testing",
  class_ind_l: "ClassInd L (All Ages)", class_ind_ten: "ClassInd 10 (Ages 10+)",
  class_ind_twelve: "ClassInd 12 (Ages 12+)", class_ind_fourteen: "ClassInd 14 (Ages 14+)",
  class_ind_sixteen: "ClassInd 16 (Ages 16+)", class_ind_eighteen: "ClassInd 18 (Ages 18+)",
  acb_g: "ACB G (General)", acb_pg: "ACB PG (Parental Guidance)", acb_m: "ACB M (Mature)",
  acb_ma15: "ACB MA15+", acb_r18: "ACB R18+ (Adults Only)", acb_rc: "ACB RC (Refused Classification)",
};

// Every age rating, in the order the filter lists them: ESRB, PEGI, then the other boards.
const AGE_RATING_OPTIONS = Object.keys(AGE_RATING_LABELS);

// IGDB game types (/v4/game_types), stored as a game's category.
const GAME_CATEGORIES = [
  "Main Game", "DLC", "Expansion", "Standalone Expansion", "Bundle", "Remake", "Remaster",
  "Expanded Game", "Port", "Fork", "Episode", "Season", "Mod", "Pack / Addon", "Update",
];

function getGameESRBLabel(esrb) {
  if (esrb === null || esrb === undefined || esrb === "") return "Not set";
  if (String(esrb).toLowerCase() === "nr") return "Not Rated";
  return AGE_RATING_LABELS[String(esrb).toLowerCase()] || String(esrb).toUpperCase();
}
