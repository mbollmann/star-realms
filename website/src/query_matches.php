<?php

$restrict_to_player = null;
$restrict_to_event = null;
if (!empty($_GET["only"])) {
    $restrict_to_player = $_GET["only"];
}
else if (!empty($_GET["event"])) {
    $restrict_to_event = $_GET["event"];
}

$db = new SQLite3("seasons.db");
if ($restrict_to_player) {
    $totalCountQuery = <<<SQL
      SELECT COUNT(*) FROM matches
        LEFT JOIN players AS player_a ON player_a.id=matches.player_a
        LEFT JOIN players AS player_b ON player_b.id=matches.player_b
        WHERE player_a.sr_name=:player OR player_b.sr_name=:player
SQL;
    $stmt = $db->prepare($totalCountQuery);
    $stmt->bindValue(':player', $restrict_to_player);
    $records = $stmt->execute();
    $recordsTotal = $records->fetchArray(SQLITE3_NUM)[0];
} else if ($restrict_to_event) {
    $totalCountQuery = <<<SQL
      SELECT COUNT(*) FROM matches
        WHERE event_id=:event
SQL;
    $stmt = $db->prepare($totalCountQuery);
    $stmt->bindValue(':event', $restrict_to_event);
    $records = $stmt->execute();
    $recordsTotal = $records->fetchArray(SQLITE3_NUM)[0];
} else {
    $totalCountQuery = "SELECT COUNT(*) FROM matches";
    $recordsTotal = $db->querySingle($totalCountQuery);
}
$recordsFiltered = $recordsTotal;

### Build the SQL query
$sort_columns = ["event", "events.tier_rank", "events.division",
                "matches.round", "srname_a", "srname_b",
                "srname_winner"];
$searchable_columns = ["event", "events.tier", "events.division", "srname_a", "srname_b"];
$query = "";
$query_select = <<<SQL
  SELECT events.name AS event, events.tier, events.division, events.id as event_id,
         matches.round,
         player_a.sr_name AS srname_a, player_b.sr_name AS srname_b,
         winner.sr_name AS srname_winner
     FROM matches
     LEFT JOIN events ON events.id=matches.event_id
     LEFT JOIN players AS player_a ON player_a.id=matches.player_a
     LEFT JOIN players AS player_b ON player_b.id=matches.player_b
     LEFT JOIN players AS winner   ON   winner.id=matches.winner_id
SQL;
$query_filter_count = <<<SQL
  SELECT COUNT(*),
         events.name AS event,
         player_a.sr_name AS srname_a, player_b.sr_name AS srname_b
     FROM matches
     LEFT JOIN events ON events.id=matches.event_id
     LEFT JOIN players AS player_a ON player_a.id=matches.player_a
     LEFT JOIN players AS player_b ON player_b.id=matches.player_b
SQL;

# Do we have a search value?
$searchValueGET = $_GET["search"]["value"];
#if (!empty($restrict_to_player)) {
#    $searchValueGET = $searchValueGET . " ^" . $restrict_to_player . "$";
#}
$searchValues = array();
$whereClauses = array();
if (!empty($searchValueGET)) {
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
    }
}
if (!empty($restrict_to_player)) {
    $i = count($searchValues);
    $searchValues[$i] = $restrict_to_player;
    $whereClauses[] = "(srname_a=:searchvalue" . $i . " OR srname_b=:searchvalue" . $i . ")";
}
if (!empty($restrict_to_event)) {
    $i = count($searchValues);
    $searchValues[$i] = $restrict_to_event;
    $whereClauses[] = "matches.event_id=:searchvalue" . $i;
}
if (!empty($whereClauses)) {
    $query .= " WHERE " . implode(" AND ", $whereClauses);
    # Count total number of filtered records
    $stmtCount = $db->prepare($query_filter_count . $query);
    if (!empty($searchValues)) {
        foreach ($searchValues as $i => $searchValue) {
            $stmtCount->bindValue(':searchvalue' . $i, $searchValues[$i]);
        }
    }
    $resultCount = $stmtCount->execute();
    $recordsFiltered = $resultCount->fetchArray()[0];
}


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
    if (!$row["srname_winner"]) {
        $row["result"] = "undecided/double loss";
    } else {
        $row["result"] = $row["srname_winner"] . " wins";
    }
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
