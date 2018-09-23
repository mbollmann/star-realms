<?php

$db = new SQLite3("seasons.db");
$totalCountQuery = "SELECT COUNT(*) FROM players";
$recordsTotal = $db->querySingle($totalCountQuery);
$recordsFiltered = $recordsTotal;

### Build the SQL query
$sort_columns = ["sr_name", "bgg_name", "events_total", "games_won", "games_won_perc"];
$searchable_columns = ["sr_name", "bgg_name"];
$query = "";
$query_select = <<<SQL
  SELECT t.bgg_name, t.sr_name,
         COUNT(m_id) AS games_total,
         COUNT(DISTINCT event_id) AS events_total,
         SUM(CASE winner_id WHEN p_id THEN 1 ELSE 0 END) AS games_won,
         1.0 * SUM(CASE winner_id WHEN p_id THEN 1 ELSE 0 END) / COUNT(m_id) AS games_won_perc
  FROM (
      SELECT p.id AS p_id, p.bgg_name, p.sr_name,
             m.id AS m_id, m.event_id, m.player_a, m.player_b, m.winner_id
      FROM players p
      LEFT JOIN matches m ON p.id = m.player_a
      UNION
      SELECT p.id, p.bgg_name, p.sr_name,
             m.id, m.event_id, m.player_a, m.player_b, m.winner_id
      FROM players p
      LEFT JOIN matches m ON p.id = m.player_b
  ) t
SQL;
#  SELECT players.bgg_name, players.sr_name,
#         COUNT(matches.id) AS games_total,
#         COUNT(DISTINCT matches.event_id) AS events_total,
#         COUNT(CASE matches.winner_id WHEN players.id THEN 1 ELSE null END) AS games_won,
#         1.0 * COUNT(CASE matches.winner_id WHEN players.id THEN 1 ELSE null END) / COUNT(matches.id) AS games_won_perc
#     FROM players
#     LEFT JOIN matches ON (matches.player_a=players.id OR matches.player_b=players.id)
#SQL;
$query_filter_count = <<<SQL
  SELECT COUNT(*) FROM players
SQL;


$query_select = <<<SQL
  SELECT t.bgg_name, t.sr_name,
         SUM(t.m_games_played) AS games_total,
         COUNT(DISTINCT t.event_id) AS events_total,
         SUM(t.m_games_won) AS games_won,
         1.0 * SUM(t.m_games_won) / SUM(t.m_games_played) AS games_won_perc
  FROM (
      SELECT p.id AS p_id, p.bgg_name, p.sr_name,
             m.games_won AS m_games_won, m.games_played AS m_games_played, m.event_id
      FROM players p
      LEFT JOIN playerinfo m ON p.id = m.player_id
  ) t
SQL;
#  SELECT players.bgg_name, players.sr_name,
#         COUNT(matches.id) AS games_total,
#         COUNT(DISTINCT matches.event_id) AS events_total,
#         COUNT(CASE matches.winner_id WHEN players.id THEN 1 ELSE null END) AS games_won,
#         1.0 * COUNT(CASE matches.winner_id WHEN players.id THEN 1 ELSE null END) / COUNT(matches.id) AS games_won_perc
#     FROM players
#     LEFT JOIN matches ON (matches.player_a=players.id OR matches.player_b=players.id)
#SQL;
$query_filter_count = <<<SQL
  SELECT COUNT(*) FROM players
SQL;

# Do we have a search value?
$searchValueGET = $_GET["search"]["value"];
if (!empty($restrict_to)) {
    $searchValueGET = $searchValueGET . " ^" . $restrict_to . "$";
}
$searchValues = array();
if (!empty($searchValueGET)) {
    $whereClauses = array();
    $searchValues = array_filter(explode(" ", $searchValueGET));
    if (!empty($searchValues)) {
        foreach ($searchValues as $i => &$searchValue) {
            # Interpret ^ and $
            if ($searchValue[0] === "^") {
                $searchValue = substr($searchValue, 1);
            } else {
                $searchValue = "%{$searchValue}";
            }
            if (substr($searchValue, -1) === "$") {
                $searchValue = substr($searchValue, 0, -1);
            } else {
                $searchValue = "{$searchValue}%";
            }

            # Build WHERE clause
            $searchTerms = array();
            foreach ($searchable_columns as $colname) {
                $searchTerms[] = $colname . ' LIKE :searchvalue' . $i;
            }
            $whereClauses[] = "(" . implode(" OR ", $searchTerms) . ")";
        }
        unset($searchValue);
        $query .= " WHERE " . implode(" AND ", $whereClauses);

        # Count total number of filtered records
        $stmtCount = $db->prepare($query_filter_count . $query);
        foreach ($searchValues as $i => $searchValue) {
            $stmtCount->bindValue(':searchvalue' . $i, $searchValues[$i]);
        }
        $resultCount = $stmtCount->execute();
        $recordsFiltered = $resultCount->fetchArray()[0];
    }
}

$query .= " GROUP BY p_id";

# Do we need to order the columns?
if (array_key_exists("order", $_GET)) {
    $orderTerms = array();
    foreach ($_GET["order"] as $order) {
        $orderIdx = (int)$order["column"];
        $orderDir = ($order["dir"] == "asc") ? " ASC" : " DESC";
        if ($orderIdx < 0 || $orderIdx >= count($sort_columns)) {
            continue;
        }
        $orderTerms[] = $sort_columns[$orderIdx] . $orderDir;
    }
    if (!empty($orderTerms)) {
        $query .= " ORDER BY " . implode(", ", $orderTerms);
    }
}

# Add limit/offset
$paramLimit = (int)$_GET["length"];
$paramOffset = (int)$_GET["start"];
$query .= " LIMIT {$paramLimit} OFFSET {$paramOffset}";

### Prepare & execute query
$query = $query_select . $query;
$stmt = $db->prepare($query);
if (!empty($searchValues)) {
    foreach ($searchValues as $i => $searchValue) {
        $stmt->bindValue(':searchvalue' . $i, $searchValue);
    }
}
$records = $stmt->execute();

$data = array();
while ($row = $records->fetchArray(SQLITE3_ASSOC)) {
    $row["games_lost"] = $row["games_total"] - $row["games_won"];
    $row["win_percentage"] = sprintf("%.2f%%", $row["games_won_perc"] * 100);
    $data[] = $row;
}

### Send JSON response
$response = array(
    "draw" => (int)$_GET["draw"],
    "recordsTotal" => $recordsTotal,
    "recordsFiltered" => $recordsFiltered,
    "data" => $data
);

echo json_encode($response);

?>
