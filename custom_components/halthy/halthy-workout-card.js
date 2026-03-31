function _sanitizeIdentifier(value) {
  if (typeof value !== "string") {
    return "";
  }
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_");
  return normalized.replace(/^_+|_+$/g, "");
}

function _entityFromUser(user) {
  const normalized = _sanitizeIdentifier(user);
  if (!normalized) {
    return "";
  }
  return `image.${normalized}_workout`;
}

function _userFromWorkoutEntity(entityId) {
  if (typeof entityId !== "string") {
    return "";
  }
  const match = /^image\.([a-z0-9_]+)_workout$/i.exec(entityId.trim());
  if (!match) {
    return "";
  }
  return _sanitizeIdentifier(match[1]);
}

function _detectHalthyUsersFromStates(states) {
  const users = new Map();
  const allStates = states && typeof states === "object" ? states : {};

  for (const [entityId, stateObj] of Object.entries(allStates)) {
    const attrs = stateObj && typeof stateObj === "object" ? stateObj.attributes || {} : {};

    const workoutUser = _userFromWorkoutEntity(entityId);
    if (workoutUser) {
      const displayName = typeof attrs.username === "string" && attrs.username.trim() ? attrs.username.trim() : workoutUser;
      users.set(workoutUser, {
        id: workoutUser,
        label: displayName,
        entity: _entityFromUser(workoutUser),
      });
      continue;
    }

    const diagnosticMatch = /^sensor\.([a-z0-9_]+)_(last_update|daily_upload_count|last_full_sync)$/i.exec(entityId);
    if (diagnosticMatch) {
      const userId = _sanitizeIdentifier(diagnosticMatch[1]);
      if (userId && !users.has(userId)) {
        users.set(userId, {
          id: userId,
          label: userId,
          entity: _entityFromUser(userId),
        });
      }
      continue;
    }

    if (typeof attrs.username === "string" && attrs.username.trim()) {
      const attrUser = _sanitizeIdentifier(attrs.username);
      if (attrUser && !users.has(attrUser)) {
        users.set(attrUser, {
          id: attrUser,
          label: attrs.username.trim(),
          entity: _entityFromUser(attrUser),
        });
      }
    }
  }

  return [...users.values()].sort((left, right) => left.label.localeCompare(right.label));
}

class HalthyWorkoutCard extends HTMLElement {
  static getStubConfig(hass) {
    const users = _detectHalthyUsersFromStates(hass && hass.states);
    if (users.length) {
      return {
        type: "custom:halthy-workout-card",
        user: users[0].id,
        entity: users[0].entity,
      };
    }

    return {
      type: "custom:halthy-workout-card",
      user: "",
      entity: "image.your_username_workout",
    };
  }

  static getConfigElement() {
    return document.createElement("halthy-workout-card-editor");
  }

  constructor() {
    super();
    this._calendarOpen = false;
    this._calendarMonth = null;
    this._selectedDayKey = "";
    this._mediaArchiveFolder = "";
    this._mediaWorkouts = [];
    this._mediaLoading = false;
    this._mediaWorkoutsLoaded = false;
    this._lastArchiveFileName = "";
    this._mediaLoadSeq = 0;
    this._imageObjectUrls = new Set();
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid configuration");
    }

    const rawEntity = typeof config.entity === "string" ? config.entity.trim() : "";
    const rawUser = typeof config.user === "string" ? config.user : "";
    const normalizedUser = _sanitizeIdentifier(rawUser);
    const derivedUserFromEntity = _userFromWorkoutEntity(rawEntity);
    const resolvedUser = normalizedUser || derivedUserFromEntity;
    const resolvedEntity = rawEntity || _entityFromUser(resolvedUser);

    if (!resolvedEntity) {
      throw new Error("`user` or `entity` is required");
    }

    this._config = {
      title: "",
      user: resolvedUser,
      entity: resolvedEntity,
      workouts_attribute: undefined,
      use_media_archive: true,
      empty_message: "No workouts found.",
      calendar_button_label: "Open Workout Calendar",
      calendar_empty_day_message: "Select a highlighted day to view its workout image.",
      ...config,
    };

    if (!this._card) {
      this._buildCard();
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._calendarOpen ? 8 : 5;
  }

  _buildCard() {
    this._card = document.createElement("ha-card");
    this._title = document.createElement("div");
    this._title.className = "card-header";

    this._content = document.createElement("div");
    this._content.className = "content";

    const style = document.createElement("style");
    style.textContent = `
      :host {
        display: block;
      }
      .content {
        padding: 0 16px 16px;
      }
      .state {
        color: var(--secondary-text-color);
        padding: 4px 0;
      }
      .section-label {
        margin-bottom: 8px;
        font-size: 0.9rem;
        color: var(--secondary-text-color);
      }
      .workout-card {
        border: none;
        background: transparent;
      }
      .latest-card-click {
        cursor: pointer;
      }
      .thumb-wrap {
        position: relative;
        aspect-ratio: 16 / 10;
        border-radius: 14px;
        overflow: hidden;
        background: linear-gradient(135deg, #d8e2ec 0%, #b7cadc 100%);
      }
      .thumb {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }
      .placeholder {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 32px;
        color: rgba(0, 0, 0, 0.35);
      }
      .meta {
        padding: 10px 0 0;
      }
      .name {
        font-weight: 600;
        line-height: 1.3;
      }
      .date {
        color: var(--secondary-text-color);
        font-size: 0.9rem;
      }
      .date-row {
        margin-top: 4px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .calendar-inline-btn {
        border: 1px solid var(--divider-color);
        background: var(--card-background-color, #fff);
        border-radius: 8px;
        width: 30px;
        height: 30px;
        min-width: 30px;
        min-height: 30px;
        padding: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: var(--primary-text-color);
        cursor: pointer;
      }
      .calendar-inline-btn[disabled] {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .calendar-inline-icon {
        --mdc-icon-size: 18px;
      }
      .chips {
        margin-top: 8px;
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .chip {
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 0.78rem;
        background: rgba(127, 127, 127, 0.15);
      }
      .calendar-btn {
        margin-top: 12px;
        padding: 8px 12px;
        border: 1px solid var(--divider-color);
        border-radius: 10px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        cursor: pointer;
        font: inherit;
      }
      .calendar-btn[disabled] {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .modal-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.45);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 16px;
        z-index: 1000;
      }
      .modal {
        width: min(700px, 100%);
        max-height: 90vh;
        overflow: auto;
        border-radius: 14px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color, #fff);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
      }
      .modal-header {
        display: grid;
        grid-template-columns: auto 1fr auto auto;
        align-items: center;
        gap: 8px;
        padding: 12px;
        border-bottom: 1px solid var(--divider-color);
      }
      .month-label {
        font-weight: 600;
        text-align: center;
      }
      .icon-btn {
        border: 1px solid var(--divider-color);
        background: var(--card-background-color, #fff);
        border-radius: 8px;
        min-width: 34px;
        min-height: 34px;
        cursor: pointer;
        color: var(--primary-text-color);
      }
      .weekdays,
      .days-grid {
        display: grid;
        grid-template-columns: repeat(7, minmax(0, 1fr));
        gap: 6px;
        padding: 0 12px;
      }
      .weekdays {
        margin-top: 12px;
      }
      .weekday {
        text-align: center;
        font-size: 0.78rem;
        color: var(--secondary-text-color);
      }
      .days-grid {
        margin-top: 8px;
        margin-bottom: 12px;
      }
      .day {
        position: relative;
        border: 1px solid var(--divider-color);
        border-radius: 10px;
        min-height: 38px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        cursor: pointer;
        font: inherit;
      }
      .day.blank {
        visibility: hidden;
        pointer-events: none;
      }
      .day.has-workout {
        border-color: var(--primary-color);
        background: rgba(33, 150, 243, 0.1);
        font-weight: 600;
      }
      .day.selected {
        outline: 2px solid var(--primary-color);
        outline-offset: 1px;
      }
      .count {
        position: absolute;
        top: 2px;
        right: 4px;
        font-size: 0.65rem;
        color: var(--secondary-text-color);
      }
      .selected-wrap {
        padding: 0 12px 12px;
      }
      .selected-note {
        margin-bottom: 8px;
        font-size: 0.85rem;
        color: var(--secondary-text-color);
      }
      @media (max-width: 520px) {
        .modal-header {
          grid-template-columns: auto 1fr auto;
        }
        .close-btn {
          grid-column: 3;
        }
      }
    `;

    this._card.appendChild(style);
    this._card.appendChild(this._title);
    this._card.appendChild(this._content);
    this.appendChild(this._card);
  }

  _render() {
    if (!this._config || !this._hass || !this._card) {
      return;
    }

    this._revokeImageObjectUrls();

    const renderedTitle = typeof this._config.title === "string" ? this._config.title.trim() : "";
    this._title.textContent = renderedTitle;
    this._title.style.display = renderedTitle ? "block" : "none";

    const entityId = this._resolvedEntityId();
    const stateObj = entityId ? this._hass.states[entityId] : null;
    if (!stateObj) {
      this._content.innerHTML = `<div class="state">Entity not found: ${this._escape(
        entityId || "image.<halthy_user>_workout"
      )}</div>`;
      return;
    }

    this._ensureMediaArchiveLoaded(stateObj);

    const attributeWorkouts = this._extractWorkouts(stateObj);
    const workouts =
      this._config.use_media_archive && this._mediaWorkouts.length
        ? this._mediaWorkouts
        : attributeWorkouts;
    const workoutsByDay = this._buildWorkoutsByDay(workouts);

    if (workouts.length && !this._calendarMonth) {
      const latestWithTime = workouts.find((workout) => workout.timestamp !== null);
      const latestDate = latestWithTime ? latestWithTime.timestamp : new Date();
      this._calendarMonth = this._firstOfMonth(latestDate);
    }
    if (!this._calendarMonth) {
      this._calendarMonth = this._firstOfMonth(new Date());
    }

    if (workouts.length && (!this._selectedDayKey || !workoutsByDay.has(this._selectedDayKey))) {
      this._selectedDayKey = workouts[0].dayKey || "";
    }

    const latest = workouts[0] || null;
    const latestHtml = latest
      ? this._renderWorkoutCard(latest, "latest-card-click", {
          showCalendarButton: true,
          calendarDisabled: !workouts.length,
        })
      : `<div class="state">${this._escape(this._config.empty_message)}</div>`;

    this._content.innerHTML = `
      ${latestHtml}
      ${
        this._config.use_media_archive && this._mediaLoading
          ? `<div class="state">Loading archived workouts from media folder...</div>`
          : ""
      }
      ${this._calendarOpen ? this._renderCalendarModal(workoutsByDay) : ""}
    `;

    this._content.querySelectorAll('[data-action="open-calendar"]').forEach((openBtn) => {
      openBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!workouts.length) {
          return;
        }
        this._calendarOpen = true;
        this._render();
      });
    });

    const closeBtn = this._content.querySelector('[data-action="close-calendar"]');
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        this._calendarOpen = false;
        this._render();
      });
    }

    const backdrop = this._content.querySelector(".modal-backdrop");
    if (backdrop) {
      backdrop.addEventListener("click", (event) => {
        if (event.target === backdrop) {
          this._calendarOpen = false;
          this._render();
        }
      });
    }

    const prevBtn = this._content.querySelector('[data-action="prev-month"]');
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        this._calendarMonth = new Date(this._calendarMonth.getFullYear(), this._calendarMonth.getMonth() - 1, 1);
        this._render();
      });
    }

    const nextBtn = this._content.querySelector('[data-action="next-month"]');
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        this._calendarMonth = new Date(this._calendarMonth.getFullYear(), this._calendarMonth.getMonth() + 1, 1);
        this._render();
      });
    }

    this._content.querySelectorAll("[data-day-key]").forEach((dayBtn) => {
      dayBtn.addEventListener("click", () => {
        const dayKey = dayBtn.getAttribute("data-day-key") || "";
        if (!dayKey || !workoutsByDay.has(dayKey)) {
          return;
        }
        this._selectedDayKey = dayKey;
        this._render();
      });
    });

    const latestCard = this._content.querySelector(".latest-card-click");
    if (latestCard) {
      latestCard.addEventListener("click", (event) => {
        if (event.target && typeof event.target.closest === "function" && event.target.closest("[data-action]")) {
          return;
        }
        this._fire("hass-more-info", { entityId });
      });
    }
  }

  _resolvedEntityId() {
    const configEntity = typeof this._config.entity === "string" ? this._config.entity.trim() : "";
    if (configEntity) {
      return configEntity;
    }
    return _entityFromUser(this._config.user);
  }

  _extractWorkouts(stateObj) {
    const attrs = stateObj.attributes || {};
    const configuredAttribute = this._config.workouts_attribute;
    const candidates = configuredAttribute
      ? [configuredAttribute]
      : ["saved_workouts", "workouts", "workout_gallery", "gallery", "items"];

    for (const key of candidates) {
      const raw = attrs[key];
      const list = this._coerceWorkoutList(raw);
      if (list.length) {
        const normalized = list.map((item) => this._normalizeWorkout(item, stateObj));
        return this._sortWorkouts(normalized);
      }
    }

    const fallback = this._fallbackSingleWorkout(stateObj);
    return fallback ? [fallback] : [];
  }

  _coerceWorkoutList(raw) {
    if (!raw) {
      return [];
    }

    if (Array.isArray(raw)) {
      return raw.filter((item) => typeof item === "object" && item !== null);
    }

    if (typeof raw === "string") {
      const trimmed = raw.trim();
      if (!trimmed) {
        return [];
      }
      try {
        const parsed = JSON.parse(trimmed);
        return this._coerceWorkoutList(parsed);
      } catch (_error) {
        return [];
      }
    }

    if (typeof raw === "object") {
      for (const key of ["saved_workouts", "workouts", "gallery", "items"]) {
        if (Array.isArray(raw[key])) {
          return raw[key].filter((item) => typeof item === "object" && item !== null);
        }
      }
    }

    return [];
  }

  _normalizeWorkout(item, stateObj) {
    const title = this._firstString(
      item.title,
      item.name,
      item.workout_type,
      item.workout_activity_type,
      item.activity_type,
      item.type,
      "Workout"
    );

    const dateSource = this._firstPresent(
      item.workout_end,
      item.end,
      item.end_time,
      item.date,
      item.workout_start,
      item.start,
      item.start_time,
      item.measurement_timestamp,
      item.last_pushed
    );
    const timestamp = this._toDate(dateSource);

    const image = this._normalizeImageUrl(
      this._firstString(
        item.archive_local_url,
        item.archive_media_source_id,
        item.image,
        item.image_url,
        item.thumbnail,
        item.thumbnail_url,
        item.map,
        item.map_url,
        item.route_map,
        item.entity_picture,
        item.picture,
        item.url
      )
    );

    return {
      title,
      timestamp,
      dayKey: timestamp ? this._dayKey(timestamp) : "",
      dateLabel: timestamp ? this._formatDate(timestamp) : this._formatDate(dateSource),
      image,
      chips: this._chipsFromWorkout(item),
      entity_id: stateObj.entity_id,
    };
  }

  _fallbackSingleWorkout(stateObj) {
    const attrs = stateObj.attributes || {};
    const imageProxyUrl = this._imageProxyUrlForState(stateObj);
    const image = this._normalizeImageUrl(
      this._firstString(
        imageProxyUrl,
        attrs.entity_picture,
        attrs.entity_picture_local,
        attrs.image,
        attrs.image_url,
        attrs.picture,
        stateObj.entity_id?.split(".")[0] === "image" ? `/api/image_proxy/${stateObj.entity_id}` : "",
        attrs.archive_media_source_id,
        attrs.archive_local_url
      )
    );

    if (!image && stateObj.entity_id?.split(".")[0] !== "image") {
      return null;
    }

    const title = this._firstString(
      attrs.workout_type,
      attrs.workout_activity_type,
      stateObj.state,
      "Workout"
    );

    const dateSource = this._firstPresent(attrs.workout_end, attrs.measurement_timestamp, attrs.last_pushed);
    const timestamp = this._toDate(dateSource);

    return {
      title,
      timestamp,
      dayKey: timestamp ? this._dayKey(timestamp) : "",
      dateLabel: timestamp ? this._formatDate(timestamp) : this._formatDate(dateSource),
      image,
      chips: this._chipsFromWorkout(attrs),
      entity_id: stateObj.entity_id,
    };
  }

  _sortWorkouts(workouts) {
    return workouts.sort((a, b) => {
      const aTime = a.timestamp ? a.timestamp.getTime() : 0;
      const bTime = b.timestamp ? b.timestamp.getTime() : 0;
      return bTime - aTime;
    });
  }

  _buildWorkoutsByDay(workouts) {
    const map = new Map();
    for (const workout of workouts) {
      if (!workout.dayKey) {
        continue;
      }
      if (!map.has(workout.dayKey)) {
        map.set(workout.dayKey, []);
      }
      map.get(workout.dayKey).push(workout);
    }
    return map;
  }

  _renderWorkoutCard(workout, extraClass = "", options = {}) {
    const imageHtml = workout.image
      ? `<img class="thumb" loading="lazy" src="${this._escapeAttr(workout.image)}" alt="${this._escapeAttr(
          workout.title || "Workout"
        )}" />`
      : `<div class="placeholder">WK</div>`;

    const chips = workout.chips
      .map((chip) => `<span class="chip">${this._escape(chip)}</span>`)
      .join("");
    const showCalendarButton = options.showCalendarButton === true;
    const calendarDisabled = options.calendarDisabled === true;
    const calendarButtonHtml = showCalendarButton
      ? `<button
          class="calendar-inline-btn"
          data-action="open-calendar"
          ${calendarDisabled ? "disabled" : ""}
          aria-label="Open workout calendar"
          title="Open workout calendar"
        >
          <ha-icon class="calendar-inline-icon" icon="mdi:calendar-month"></ha-icon>
        </button>`
      : "";
    const dateRowHtml = workout.dateLabel || calendarButtonHtml
      ? `<div class="date-row">
          ${workout.dateLabel ? `<div class="date">${this._escape(workout.dateLabel)}</div>` : "<div></div>"}
          ${calendarButtonHtml}
        </div>`
      : "";

    return `
      <article class="workout-card ${this._escapeAttr(extraClass)}">
        <div class="thumb-wrap">${imageHtml}</div>
        <div class="meta">
          <div class="name">${this._escape(workout.title || "Workout")}</div>
          ${dateRowHtml}
          ${chips ? `<div class="chips">${chips}</div>` : ""}
        </div>
      </article>
    `;
  }

  _renderCalendarModal(workoutsByDay) {
    const monthLabel = new Intl.DateTimeFormat(undefined, {
      month: "long",
      year: "numeric",
    }).format(this._calendarMonth);

    const weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const weekdayHtml = weekdays.map((day) => `<div class="weekday">${day}</div>`).join("");

    const calendarGrid = this._renderCalendarGrid(workoutsByDay);
    const selectedWorkouts = this._selectedDayKey ? workoutsByDay.get(this._selectedDayKey) || [] : [];
    const selectedWorkout = selectedWorkouts[0] || null;
    const selectedMessage = this._config.calendar_empty_day_message;

    const selectedHtml = selectedWorkout
      ? `
        <div class="selected-note">${selectedWorkouts.length} workout${
          selectedWorkouts.length === 1 ? "" : "s"
        } on this day</div>
        ${this._renderWorkoutCard(selectedWorkout, "selected-card")}
      `
      : `<div class="state">${this._escape(selectedMessage)}</div>`;

    return `
      <div class="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true" aria-label="Workout Calendar">
          <div class="modal-header">
            <button class="icon-btn" data-action="prev-month" aria-label="Previous month">&#8249;</button>
            <div class="month-label">${this._escape(monthLabel)}</div>
            <button class="icon-btn" data-action="next-month" aria-label="Next month">&#8250;</button>
            <button class="icon-btn close-btn" data-action="close-calendar" aria-label="Close">X</button>
          </div>
          <div class="weekdays">${weekdayHtml}</div>
          <div class="days-grid">${calendarGrid}</div>
          <div class="selected-wrap">${selectedHtml}</div>
        </div>
      </div>
    `;
  }

  _renderCalendarGrid(workoutsByDay) {
    const year = this._calendarMonth.getFullYear();
    const month = this._calendarMonth.getMonth();

    const firstOfMonth = new Date(year, month, 1);
    const mondayIndex = (firstOfMonth.getDay() + 6) % 7;
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const cells = [];

    for (let i = 0; i < mondayIndex; i += 1) {
      cells.push('<button class="day blank" disabled aria-hidden="true"></button>');
    }

    for (let day = 1; day <= daysInMonth; day += 1) {
      const dayKey = this._dayKeyFromParts(year, month + 1, day);
      const hasWorkout = workoutsByDay.has(dayKey);
      const selected = this._selectedDayKey === dayKey;
      const count = hasWorkout ? workoutsByDay.get(dayKey).length : 0;

      cells.push(`
        <button
          class="day ${hasWorkout ? "has-workout" : ""} ${selected ? "selected" : ""}"
          ${hasWorkout ? `data-day-key="${dayKey}"` : "disabled"}
          aria-label="${dayKey}"
        >
          ${day}
          ${count > 1 ? `<span class="count">${count}</span>` : ""}
        </button>
      `);
    }

    while (cells.length % 7 !== 0) {
      cells.push('<button class="day blank" disabled aria-hidden="true"></button>');
    }

    return cells.join("");
  }

  _chipsFromWorkout(item) {
    const chips = [];

    const distanceM = this._toNumber(item.workout_distance_m ?? item.distance_m ?? item.distance);
    if (distanceM !== null && distanceM > 0) {
      const km = distanceM / 1000;
      chips.push(`${km.toFixed(km >= 10 ? 0 : 1)} km`);
    }

    const durationS = this._toNumber(
      item.workout_duration_s ?? item.duration_s ?? item.duration_seconds ?? item.duration
    );
    if (durationS !== null && durationS > 0) {
      const minutes = Math.round(durationS / 60);
      chips.push(`${minutes} min`);
    }

    const kcal = this._toNumber(item.workout_active_energy_kcal ?? item.active_energy_kcal ?? item.energy_kcal);
    if (kcal !== null && kcal > 0) {
      chips.push(`${Math.round(kcal)} kcal`);
    }

    const hr = this._toNumber(item.workout_avg_heart_rate_bpm ?? item.avg_heart_rate_bpm);
    if (hr !== null && hr > 0) {
      chips.push(`${Math.round(hr)} bpm`);
    }

    return chips;
  }

  _ensureMediaArchiveLoaded(stateObj) {
    if (!this._config.use_media_archive || !this._hass || typeof this._hass.callWS !== "function") {
      return;
    }

    const attrs = stateObj.attributes || {};
    const folder = this._detectArchiveFolder(attrs);
    if (!folder) {
      return;
    }

    const archiveFileName = this._firstString(attrs.archive_file_name);
    const folderChanged = folder !== this._mediaArchiveFolder;
    const hasNewLatestFile = !!archiveFileName && archiveFileName !== this._lastArchiveFileName;

    if (archiveFileName) {
      this._lastArchiveFileName = archiveFileName;
    }

    if (
      !folderChanged &&
      !hasNewLatestFile &&
      (this._mediaLoading || this._mediaWorkoutsLoaded)
    ) {
      return;
    }

    this._mediaArchiveFolder = folder;
    void this._loadMediaArchiveWorkouts(folder, stateObj.entity_id);
  }

  async _loadMediaArchiveWorkouts(folder, entityId) {
    const loadSeq = ++this._mediaLoadSeq;
    this._mediaLoading = true;
    this._mediaWorkoutsLoaded = false;
    this._render();

    try {
      const mediaContentId = `media-source://media_source/local/${folder}`;
      const response = await this._hass.callWS({
        type: "media_source/browse_media",
        media_content_id: mediaContentId,
      });

      const children = Array.isArray(response?.children) ? response.children : [];
      const workouts = (
        await Promise.all(
          children
            .filter((child) => this._isImageMediaChild(child))
            .map((child) => this._workoutFromMediaChildAsync(child, entityId))
        )
      ).filter((item) => item !== null);

      this._sortWorkouts(workouts);
      if (loadSeq !== this._mediaLoadSeq) {
        return;
      }
      this._mediaWorkouts = workouts;
    } catch (_error) {
      if (loadSeq !== this._mediaLoadSeq) {
        return;
      }
      this._mediaWorkouts = [];
    } finally {
      if (loadSeq !== this._mediaLoadSeq) {
        return;
      }
      this._mediaLoading = false;
      this._mediaWorkoutsLoaded = true;
      this._render();
    }
  }

  _detectArchiveFolder(attrs) {
    const archiveRelativePath = this._firstString(attrs.archive_relative_path);
    if (archiveRelativePath) {
      return this._parentPath(archiveRelativePath);
    }

    const archiveLocalUrl = this._firstString(attrs.archive_local_url);
    const relativeFromLocal = this._relativePathFromLocalUrl(archiveLocalUrl);
    if (relativeFromLocal) {
      return this._parentPath(relativeFromLocal);
    }

    const archiveMediaSourceId = this._firstString(attrs.archive_media_source_id);
    const relativeFromMediaSource = this._relativePathFromMediaSourceId(archiveMediaSourceId);
    if (relativeFromMediaSource) {
      return this._parentPath(relativeFromMediaSource);
    }

    return "";
  }

  _isImageMediaChild(child) {
    if (!child || typeof child !== "object") {
      return false;
    }
    if (child.media_class === "image") {
      return true;
    }
    if (typeof child.media_content_type === "string" && child.media_content_type.startsWith("image/")) {
      return true;
    }
    const title = this._firstString(child.title);
    return /\.(png|jpe?g|webp|gif|bmp|svg)$/i.test(title);
  }

  async _workoutFromMediaChildAsync(child, entityId) {
    const mediaSourceId = this._firstString(child.media_content_id);
    const relativePath = this._relativePathFromMediaSourceId(mediaSourceId);
    if (!relativePath) {
      return null;
    }

    const fileName = relativePath.split("/").pop() || "";
    const timestamp =
      this._archiveTimestampFromFileName(fileName) ||
      this._toDate(child.modified_at) ||
      this._toDate(child.created_at);

    const dateLabel = timestamp ? this._formatDate(timestamp) : "";
    const dayKey = timestamp ? this._dayKey(timestamp) : "";

    const resolvedImage = await this._resolvedMediaImageUrl(child, mediaSourceId, relativePath);

    return {
      title: "Workout",
      timestamp,
      dayKey,
      dateLabel,
      image: resolvedImage,
      chips: [],
      entity_id: entityId,
    };
  }

  async _resolvedMediaImageUrl(child, mediaSourceId, relativePath) {
    const preferredDirect = this._normalizeImageUrl(this._firstString(child.thumbnail, child.url));
    const preferredAuthSafe = await this._authSafeImageUrl(preferredDirect);
    if (preferredAuthSafe) {
      return preferredAuthSafe;
    }

    const resolvedViaMediaSource = await this._resolveMediaSourceUrl(mediaSourceId);
    const resolvedMediaSourceAuthSafe = await this._authSafeImageUrl(resolvedViaMediaSource);
    if (resolvedMediaSourceAuthSafe) {
      return resolvedMediaSourceAuthSafe;
    }

    return await this._authSafeImageUrl(this._normalizeImageUrl(`/media/local/${relativePath}`));
  }

  _isProtectedMediaLocalUrl(url) {
    if (!url || typeof url !== "string") {
      return false;
    }
    const normalized = url.trim().toLowerCase();
    return normalized.startsWith("/media/local/") || normalized.includes("/media/local/");
  }

  async _resolveMediaSourceUrl(mediaSourceId) {
    if (!mediaSourceId || typeof mediaSourceId !== "string") {
      return null;
    }
    if (!this._hass || typeof this._hass.callWS !== "function") {
      return null;
    }

    try {
      const resolved = await this._hass.callWS({
        type: "media_source/resolve_media",
        media_content_id: mediaSourceId,
      });
      const resolvedUrl = this._firstString(resolved?.url);
      if (!resolvedUrl) {
        return null;
      }
      return this._normalizeImageUrl(resolvedUrl);
    } catch (_error) {
      return null;
    }
  }

  async _authSafeImageUrl(url) {
    const normalized = this._normalizeImageUrl(url);
    if (!normalized) {
      return null;
    }
    if (!this._isProtectedMediaLocalUrl(normalized)) {
      return normalized;
    }

    const absoluteUrl = this._absoluteUrl(normalized);
    const token = this._hass?.auth?.data?.access_token;
    if (!absoluteUrl || !token || typeof fetch !== "function") {
      return null;
    }

    try {
      const response = await fetch(absoluteUrl, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        credentials: "omit",
      });
      if (!response.ok) {
        return null;
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      this._imageObjectUrls.add(objectUrl);
      return objectUrl;
    } catch (_error) {
      return null;
    }
  }

  _absoluteUrl(url) {
    if (!url || typeof url !== "string") {
      return "";
    }
    const trimmed = url.trim();
    if (!trimmed) {
      return "";
    }
    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      return trimmed;
    }
    if (this._hass && typeof this._hass.hassUrl === "function") {
      try {
        return this._hass.hassUrl(trimmed.startsWith("/") ? trimmed : `/${trimmed}`);
      } catch (_error) {
        return trimmed;
      }
    }
    return trimmed;
  }

  _revokeImageObjectUrls() {
    if (!this._imageObjectUrls || !this._imageObjectUrls.size) {
      return;
    }
    for (const objectUrl of this._imageObjectUrls) {
      try {
        URL.revokeObjectURL(objectUrl);
      } catch (_error) {
        // No-op.
      }
    }
    this._imageObjectUrls.clear();
  }

  disconnectedCallback() {
    this._revokeImageObjectUrls();
  }

  _imageProxyUrlForState(stateObj) {
    if (!stateObj || typeof stateObj !== "object") {
      return "";
    }
    if (typeof stateObj.entity_id !== "string" || !stateObj.entity_id.trim()) {
      return "";
    }
    const attrs = stateObj.attributes || {};
    const accessToken = this._firstString(attrs.access_token);
    const base = `/api/image_proxy/${stateObj.entity_id}`;
    if (!accessToken) {
      return base;
    }
    return `${base}?token=${encodeURIComponent(accessToken)}`;
  }

  _archiveTimestampFromFileName(fileName) {
    const match = /^(\d{8})T(\d{6})Z_/.exec(fileName);
    if (!match) {
      return null;
    }

    const dateToken = match[1];
    const timeToken = match[2];
    const year = Number(dateToken.slice(0, 4));
    const month = Number(dateToken.slice(4, 6));
    const day = Number(dateToken.slice(6, 8));
    const hour = Number(timeToken.slice(0, 2));
    const minute = Number(timeToken.slice(2, 4));
    const second = Number(timeToken.slice(4, 6));

    if (
      [year, month, day, hour, minute, second].some((value) => !Number.isFinite(value))
    ) {
      return null;
    }

    return new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  }

  _relativePathFromMediaSourceId(mediaSourceId) {
    if (!mediaSourceId || typeof mediaSourceId !== "string") {
      return "";
    }
    const prefix = "media-source://media_source/local/";
    if (!mediaSourceId.startsWith(prefix)) {
      return "";
    }
    return mediaSourceId.slice(prefix.length).replace(/^\/+/, "");
  }

  _relativePathFromLocalUrl(localUrl) {
    if (!localUrl || typeof localUrl !== "string") {
      return "";
    }
    const prefix = "/media/local/";
    if (!localUrl.startsWith(prefix)) {
      return "";
    }
    return localUrl.slice(prefix.length).replace(/^\/+/, "");
  }

  _parentPath(pathValue) {
    if (!pathValue || typeof pathValue !== "string") {
      return "";
    }
    const normalized = pathValue.replace(/^\/+/, "").replace(/\/+$/, "");
    const slashIndex = normalized.lastIndexOf("/");
    if (slashIndex <= 0) {
      return "";
    }
    return normalized.slice(0, slashIndex);
  }

  _toDate(value) {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return value;
    }

    if (typeof value === "number" && Number.isFinite(value)) {
      const epochMs = value > 1e12 ? value : value * 1000;
      const parsedNumber = new Date(epochMs);
      return Number.isNaN(parsedNumber.getTime()) ? null : parsedNumber;
    }

    if (typeof value !== "string") {
      return null;
    }

    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }

    const numeric = Number(trimmed.replace(",", "."));
    if (Number.isFinite(numeric)) {
      const epochMs = numeric > 1e12 ? numeric : numeric * 1000;
      const parsedNumeric = new Date(epochMs);
      if (!Number.isNaN(parsedNumeric.getTime())) {
        return parsedNumeric;
      }
    }

    const parsed = new Date(trimmed);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  _normalizeImageUrl(url) {
    if (!url || typeof url !== "string") {
      return null;
    }

    const trimmed = url.trim();
    if (!trimmed) {
      return null;
    }

    const relativeFromMediaSource = this._relativePathFromMediaSourceId(trimmed);
    if (relativeFromMediaSource) {
      return `/media/local/${relativeFromMediaSource}`;
    }

    if (trimmed.startsWith("data:image/")) {
      return trimmed;
    }

    if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      return trimmed;
    }

    if (trimmed.startsWith("/")) {
      if (this._hass && typeof this._hass.hassUrl === "function") {
        try {
          return this._hass.hassUrl(trimmed);
        } catch (_error) {
          return trimmed;
        }
      }
      return trimmed;
    }

    return `/${trimmed.replace(/^\/+/, "")}`;
  }

  _toNumber(value) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string") {
      const n = Number(value.replace(",", "."));
      return Number.isFinite(n) ? n : null;
    }
    return null;
  }

  _firstPresent(...values) {
    for (const value of values) {
      if (value === null || value === undefined) {
        continue;
      }
      if (typeof value === "string" && !value.trim()) {
        continue;
      }
      return value;
    }
    return null;
  }

  _firstString(...values) {
    for (const value of values) {
      if (typeof value === "string") {
        const trimmed = value.trim();
        if (trimmed) {
          return trimmed;
        }
      }
    }
    return "";
  }

  _dayKey(date) {
    return this._dayKeyFromParts(date.getFullYear(), date.getMonth() + 1, date.getDate());
  }

  _dayKeyFromParts(year, month, day) {
    return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }

  _firstOfMonth(date) {
    return new Date(date.getFullYear(), date.getMonth(), 1);
  }

  _formatDate(value) {
    const parsed = value instanceof Date ? value : this._toDate(value);
    if (!parsed) {
      return typeof value === "string" ? value : "";
    }
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(parsed);
  }

  _fire(type, detail = {}) {
    this.dispatchEvent(
      new CustomEvent(type, {
        detail,
        bubbles: true,
        composed: true,
      })
    );
  }

  _escape(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  _escapeAttr(value) {
    return this._escape(value).replace(/`/g, "&#096;");
  }
}

class HalthyWorkoutCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      type: "custom:halthy-workout-card",
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._users = _detectHalthyUsersFromStates(hass && hass.states);
    this._render();
  }

  _render() {
    if (!this._config) {
      return;
    }

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    const users = Array.isArray(this._users) ? this._users : [];
    const selectedUser = _sanitizeIdentifier(this._config.user || _userFromWorkoutEntity(this._config.entity));
    const defaultEntity = _entityFromUser(selectedUser);
    const entityValue =
      typeof this._config.entity === "string" && this._config.entity.trim()
        ? this._config.entity.trim()
        : defaultEntity;

    const userOptions = users
      .map((user) => {
        const selected = user.id === selectedUser ? "selected" : "";
        return `<option value="${this._escapeAttr(user.id)}" ${selected}>${this._escape(user.label)}</option>`;
      })
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        .wrapper {
          display: grid;
          gap: 12px;
        }
        .field {
          display: grid;
          gap: 6px;
        }
        label {
          font-size: 0.9rem;
          color: var(--primary-text-color);
        }
        input,
        select {
          width: 100%;
          box-sizing: border-box;
          min-height: 38px;
          border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
          padding: 8px 10px;
          font: inherit;
        }
        .hint {
          color: var(--secondary-text-color);
          font-size: 0.8rem;
        }
        .toggle-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
      </style>
      <div class="wrapper">
        <div class="field">
          <label for="user">Halthy user</label>
          <select id="user">
            <option value="">Manual entity</option>
            ${userOptions}
          </select>
          <div class="hint">
            ${
              users.length
                ? "Users are auto-detected from your Halthy integration entities."
                : "No Halthy users detected yet. Keep manual entity or wait for first sync."
            }
          </div>
        </div>

        <div class="field">
          <label for="entity">Workout image entity</label>
          <input id="entity" type="text" placeholder="image.username_workout" value="${this._escapeAttr(
            entityValue
          )}" />
        </div>

        <div class="field">
          <label for="title">Title</label>
          <input id="title" type="text" value="${this._escapeAttr(this._config.title || "")}" />
        </div>

        <div class="field">
          <label for="workouts_attribute">Workouts attribute (optional)</label>
          <input id="workouts_attribute" type="text" value="${this._escapeAttr(
            this._config.workouts_attribute || ""
          )}" />
        </div>

        <div class="toggle-row">
          <input id="use_media_archive" type="checkbox" ${
            this._config.use_media_archive !== false ? "checked" : ""
          } />
          <label for="use_media_archive">Use media archive from Halthy integration</label>
        </div>
      </div>
    `;

    const userSelect = this.shadowRoot.getElementById("user");
    const entityInput = this.shadowRoot.getElementById("entity");
    const titleInput = this.shadowRoot.getElementById("title");
    const workoutsAttributeInput = this.shadowRoot.getElementById("workouts_attribute");
    const mediaArchiveInput = this.shadowRoot.getElementById("use_media_archive");

    if (userSelect) {
      userSelect.value = users.find((user) => user.id === selectedUser) ? selectedUser : "";
      userSelect.addEventListener("change", (event) => {
        const nextUser = _sanitizeIdentifier(event.target.value);
        if (nextUser) {
          this._emitConfig({
            user: nextUser,
            entity: _entityFromUser(nextUser),
          });
          return;
        }
        this._emitConfig({
          user: "",
        });
      });
    }

    if (entityInput) {
      entityInput.addEventListener("change", (event) => {
        const nextEntity = String(event.target.value || "").trim();
        const nextUser = _userFromWorkoutEntity(nextEntity);
        this._emitConfig({
          entity: nextEntity,
          user: nextUser,
        });
      });
    }

    if (titleInput) {
      titleInput.addEventListener("change", (event) => {
        this._emitConfig({
          title: String(event.target.value || ""),
        });
      });
    }

    if (workoutsAttributeInput) {
      workoutsAttributeInput.addEventListener("change", (event) => {
        const value = String(event.target.value || "").trim();
        this._emitConfig({
          workouts_attribute: value || undefined,
        });
      });
    }

    if (mediaArchiveInput) {
      mediaArchiveInput.addEventListener("change", (event) => {
        this._emitConfig({
          use_media_archive: !!event.target.checked,
        });
      });
    }
  }

  _emitConfig(patch) {
    const nextConfig = {
      ...this._config,
      ...patch,
    };
    if (!nextConfig.type) {
      nextConfig.type = "custom:halthy-workout-card";
    }

    if ((!nextConfig.entity || !String(nextConfig.entity).trim()) && nextConfig.user) {
      nextConfig.entity = _entityFromUser(nextConfig.user);
    }

    this._config = nextConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: nextConfig },
        bubbles: true,
        composed: true,
      })
    );
    this._render();
  }

  _escape(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  _escapeAttr(value) {
    return this._escape(value).replace(/`/g, "&#096;");
  }
}

if (!customElements.get("halthy-workout-card")) {
  customElements.define("halthy-workout-card", HalthyWorkoutCard);
}

if (!customElements.get("halthy-workout-card-editor")) {
  customElements.define("halthy-workout-card-editor", HalthyWorkoutCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.find((card) => card.type === "halthy-workout-card")) {
  window.customCards.push({
    type: "halthy-workout-card",
    name: "Halthy Workout Card",
    description:
      "Shows the latest workout by default and opens a calendar popup with highlighted workout days.",
    preview: true,
    documentationURL: "https://github.com/Mosher23/Halthy-Bridge",
  });
}
