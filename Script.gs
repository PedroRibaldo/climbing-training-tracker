/**
 * Web App bridge between the Climbing Training Tracker's Android widgets
 * and Supabase.
 *
 * Before deploying, set three secret Script Properties:
 *   Project Settings > Script Properties > Add property
 *     API_TOKEN     - same shared secret the widgets already send
 *     SUPABASE_URL  - e.g. https://xxxxx.supabase.co
 *     SUPABASE_KEY  - Supabase service_role key
 */

function getApiToken_() {
  return PropertiesService.getScriptProperties().getProperty('API_TOKEN');
}

function jsonResponse_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Entry point for both widgets. Routes on ?action=log_session or
 * ?action=add_exercise. The API_TOKEN travels in the JSON body, not a
 * header (Apps Script can't read custom request headers).
 */
function doPost(e) {
  try {
    const action = e.parameter.action;
    const body = JSON.parse(e.postData.contents);

    if (!body.token || body.token !== getApiToken_()) {
      return jsonResponse_({ success: false, error: 'Unauthorized' });
    }

    if (action === 'log_session') {
      return logSession_(body);
    }
    if (action === 'add_exercise') {
      return addExercise_(body);
    }
    return jsonResponse_({ success: false, error: 'Unknown action: ' + action });

  } catch (err) {
    return jsonResponse_({ success: false, error: err.message });
  }
}

/**
 * Optional read endpoint, e.g. to double-check the current exercise list
 * before typing exercise names into the log-session widget.
 * Usage: GET <webapp-url>?token=<API_TOKEN>
 */
function doGet(e) {
  if (!e.parameter.token || e.parameter.token !== getApiToken_()) {
    return jsonResponse_({ success: false, error: 'Unauthorized' });
  }

  try {
    const rows = supabaseRequest_('GET', 'exercise?select=name&order=name.asc', null);
    const names = rows.map(function (r) { return r.name; });
    return jsonResponse_({ success: true, exercises: names });
  } catch (err) {
    return jsonResponse_({ success: false, error: err.message });
  }
}

// ============================================================
// Supabase REST helpers
// ============================================================

function supabaseHeaders_(extra) {
  const key = PropertiesService.getScriptProperties().getProperty('SUPABASE_KEY');
  const headers = {
    'apikey': key,
    'Authorization': 'Bearer ' + key,
    'Content-Type': 'application/json'
  };
  for (const k in (extra || {})) {
    headers[k] = extra[k];
  }
  return headers;
}

function supabaseUrl_(path) {
  const base = PropertiesService.getScriptProperties().getProperty('SUPABASE_URL');
  return base.replace(/\/$/, '') + '/rest/v1/' + path;
}

/**
 * One helper for every Supabase REST call. Throws on any 4xx/5xx so
 * callers don't have to check response codes themselves - doPost's
 * try/catch turns that into a normal { success: false, error } reply.
 */
function supabaseRequest_(method, path, payload, extraHeaders) {
  const options = {
    method: method,
    headers: supabaseHeaders_(extraHeaders),
    muteHttpExceptions: true
  };
  if (payload !== undefined && payload !== null) {
    options.payload = JSON.stringify(payload);
  }

  const response = UrlFetchApp.fetch(supabaseUrl_(path), options);
  const code = response.getResponseCode();
  const text = response.getContentText();

  if (code >= 400) {
    throw new Error('Supabase ' + method + ' ' + path + ' failed (' + code + '): ' + text);
  }
  return text ? JSON.parse(text) : null;
}

/** Converts the widget's DD/MM/YYYY date string to Postgres' ISO format. */
function ddmmyyyyToIso_(dateStr) {
  if (!dateStr) return null;
  const parts = dateStr.split('/');
  if (parts.length !== 3) return null;
  const dd = parts[0].padStart(2, '0');
  const mm = parts[1].padStart(2, '0');
  const yyyy = parts[2];
  return yyyy + '-' + mm + '-' + dd;
}

// ============================================================
// Actions
// ============================================================

/**
 * Inserts one row into climbing_training, then links any named exercises
 * via training_exercises
 *
 * Expected body fields:
 *   date          "DD/MM/YYYY"
 *   category      "Strength" | "Stamina" | "Technique" | "Free" | "Rest"
 *   effort        number 1-10
 *   gym_grade     e.g. "Blue"
 *   moonboard_grade  e.g. "V4"
 *   injured       boolean
 *   exercises     comma-separated string, e.g. "Pull-ups, Hangboard"
 */
function logSession_(body) {
  const isoDate = ddmmyyyyToIso_(body.date);
  if (!isoDate) {
    return jsonResponse_({ success: false, error: 'Invalid or missing date: ' + body.date });
  }

  const sessionRow = {
    date_entry: new Date().toISOString(),
    date: isoDate,
    category: body.category || null,
    effort: (body.effort === undefined || body.effort === '') ? null : Number(body.effort),
    gym_grade: body.gym_grade || null,
    moonboard_grade: body.moonboard_grade || null,
    injured: !!body.injured
  };

  const inserted = supabaseRequest_('POST', 'climbing_training', sessionRow, { 'Prefer': 'return=representation' });
  if (!inserted || !inserted.length) {
    return jsonResponse_({ success: false, error: 'Session insert returned no data - check the SUPABASE_KEY is a service_role key.' });
  }
  const sessionId = inserted[0].id;

  const unmatched = linkExercises_(sessionId, body.exercises);

  return jsonResponse_({ success: true, id: sessionId, unmatched_exercises: unmatched });
}

/**
 * Looks up each comma-separated exercise name against the exercise table
 * and creates the matching training_exercises links. Names that don't
 * match anything are skipped and returned, not silently dropped
 */
function linkExercises_(sessionId, exercisesStr) {
  if (!exercisesStr) return [];

  const names = exercisesStr.split(',')
    .map(function (n) { return n.trim(); })
    .filter(function (n) { return n; });
  if (!names.length) return [];

  const inList = names.map(encodeURIComponent).join(',');
  const matches = supabaseRequest_('GET', 'exercise?select=id,name&name=in.(' + inList + ')', null);

  const nameToId = {};
  matches.forEach(function (row) { nameToId[row.name] = row.id; });

  const unmatched = names.filter(function (n) { return !(n in nameToId); });
  const junctionRows = names
    .filter(function (n) { return n in nameToId; })
    .map(function (n) { return { training_id: sessionId, exercise_id: nameToId[n] }; });

  if (junctionRows.length) {
    supabaseRequest_('POST', 'training_exercises', junctionRows, { 'Prefer': 'return=minimal' });
  }
  return unmatched;
}

/**
 * Inserts one row into the exercise table.
 *
 * Expected body fields:
 *   name       required
 *   type       "Reps" | "Time"
 *   sets       number of sets
 *   reps       number of reps (only meaningful when type is "Reps")
 *   time       duration string, e.g. "00:15" (only meaningful when type is "Time")
 *   rest       number
 *   comments   free text, optional
 *   phase      "Before" | "During" | "After"
 */
function addExercise_(body) {
  if (!body.name || body.name.toString().trim() === '') {
    return jsonResponse_({ success: false, error: 'Exercise name is required' });
  }

  const exerciseRow = {
    name: body.name,
    type: body.type || null,
    sets: (body.sets === undefined || body.sets === '') ? null : Number(body.sets),
    reps: (body.reps === undefined || body.reps === '') ? null : Number(body.reps),
    time: body.time || null,
    rest: (body.rest === undefined || body.rest === '') ? null : Number(body.rest),
    comments: body.comments || null,
    phase: body.phase || null
  };

  supabaseRequest_('POST', 'exercise', exerciseRow, { 'Prefer': 'return=minimal' });
  return jsonResponse_({ success: true });
}