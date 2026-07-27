/**
 * Web App backend for the Climbing Training Tracker
 *
 * Before deploying, set a secret token:
 *   Project Settings > Script Properties > Add property
 *     key:   API_TOKEN
 *     value: <a random string you generate once>
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
 * ?action=add_exercise.The token travels in the JSON body, not a header
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

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Exercise_Dictionary');
  const data = sheet.getDataRange().getValues();
  const names = data.slice(1)
    .map(function (row) { return row[0]; })
    .filter(function (name) { return name && name.toString().trim() !== ''; });

  return jsonResponse_({ success: true, exercises: names });
}

/**
 * Appends one row to Main_Log. Column order matches COL_MAPPING and
 * DICT_COLUMN_NAMES in data_pipeline.py
 *
 * Expected body fields:
 *   date          "DD/MM/YYYY"
 *   category      "Strength" | "Stamina" | "Technique" | "Free" | "Rest"
 *   effort        number 1-10
 *   gym_grade     e.g. "Blue"   (must match PipelineConfig.GYM_MAPPING keys)
 *   moonboard_grade  e.g. "V4" (must match PipelineConfig.MOONBOARD_MAPPING keys)
 *   injured       boolean
 *   exercises     comma-separated string, e.g. "Pull-ups, Hangboard"
 */
function logSession_(body) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Main_Log');

  const timestamp = Utilities.formatDate(
    new Date(), Session.getScriptTimeZone(), 'dd/MM/yyyy HH:mm:ss'
  );

  sheet.appendRow([
    timestamp,                       // Carimbo de data/hora
    body.date || '',                 // Date
    body.category || '',             // Category
    body.effort || '',               // Effort Scale
    body.gym_grade || '',            // Max Gym Grade Color
    body.moonboard_grade || '',      // Max Moonboard Grade
    body.injured ? 'Yes' : 'No',     // Injuries / Tweaks
    body.exercises || ''             // Exercises
  ]);

  return jsonResponse_({ success: true });
}

/**
 * Appends one row to Exercise_Dictionary.
 *
 * Expected body fields:
 *   name       required
 *   type       either "Reps" or "Time"
 *   sets       number of sets
 *   reps       reps or duration, e.g. "12" or "00:15" (mm:ss)
 *   rest       number in minutes
 *   comments   free text, optional
 */
function addExercise_(body) {
  if (!body.name || body.name.toString().trim() === '') {
    return jsonResponse_({ success: false, error: 'Exercise name is required' });
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Exercise_Dictionary');

  sheet.appendRow([
    body.name,
    body.type || '',
    body.sets || '',
    body.reps || '',
    body.rest || '',
    body.comments || ''
  ]);

  return jsonResponse_({ success: true });
}