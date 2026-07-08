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
    this._selectedWorkoutIndex = 0;
    this._currentWorkoutIndex = 0;
    this._mediaWorkouts = [];
    this._mediaLoading = false;
    this._mediaWorkoutsLoaded = false;
    this._lastArchiveFileName = "";
    this._mediaLoadSeq = 0;
    this._apiArchiveWorkouts = [];
    this._apiLoading = false;
    this._apiWorkoutsLoaded = false;
    this._apiLoadSeq = 0;
    this._apiArchiveUser = "";
    this._imageObjectUrls = new Set();
    this._lastStateSignature = "";
    this._mediaArchiveFoldersKey = "";
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
      calendar_icon: "mdi:calendar-month",
      calendar_button_label: "Open Workout Calendar",
      calendar_empty_day_message: "Select a highlighted day to view its workout image.",
      ...config,
    };
    this._lastStateSignature = "";
    this._apiArchiveUser = "";
    this._apiWorkoutsLoaded = false;
    this._apiArchiveWorkouts = [];
    this._selectedWorkoutIndex = 0;
    this._currentWorkoutIndex = 0;

    if (!this._card) {
      this._buildCard();
    }

    if (this._hass && this._card) {
      this._render();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config || !this._card) {
      return;
    }

    const entityId = this._resolvedEntityId();
    const nextStateObj = entityId ? hass.states?.[entityId] : null;
    const nextSignature = this._stateSignature(nextStateObj);
    if (!this._lastStateSignature) {
      this._lastStateSignature = nextSignature;
      this._render();
      return;
    }
    if (nextSignature !== this._lastStateSignature) {
      this._lastStateSignature = nextSignature;
      this._render();
    }
  }

  getCardSize() {
    return this._calendarOpen ? 10 : 5;
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
        padding: 0 0 16px;
      }
      .state {
        color: var(--secondary-text-color);
        padding: 4px 16px;
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
        border-radius: 14px;
        overflow: hidden;
        background: transparent;
        line-height: 0;
      }
      .workout-nav-btn {
        position: absolute;
        top: 50%;
        transform: translateY(-50%);
        width: 44px;
        height: 44px;
        border: none;
        border-radius: 999px;
        background: rgba(0, 0, 0, 0.5);
        color: #fff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        line-height: 1;
        z-index: 2;
        transition: background 120ms ease, transform 120ms ease, opacity 120ms ease;
      }
      .workout-nav-btn:hover {
        background: rgba(0, 0, 0, 0.62);
      }
      .workout-nav-btn:active {
        transform: translateY(-50%) scale(0.96);
      }
      .workout-nav-btn.left {
        left: 12px;
      }
      .workout-nav-btn.right {
        right: 12px;
      }
      .workout-nav-btn ha-icon {
        --mdc-icon-size: 28px;
      }
      .thumb {
        width: 100%;
        height: auto;
        object-fit: contain;
        display: block;
      }
      .placeholder {
        width: 100%;
        min-height: 220px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 32px;
        color: rgba(0, 0, 0, 0.35);
      }
      .meta {
        padding: 10px 16px 0;
      }
      .headline-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .headline-main {
        display: flex;
        align-items: baseline;
        gap: 8px;
        flex-wrap: wrap;
        min-width: 0;
      }
      .name {
        font-weight: 600;
        line-height: 1.3;
      }
      .date {
        color: var(--secondary-text-color);
        font-size: 0.9rem;
      }
      .calendar-inline-btn {
        border: none;
        background: transparent;
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
        align-self: flex-start;
      }
      .calendar-inline-btn[disabled] {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .calendar-inline-icon {
        --mdc-icon-size: 29px;
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
        width: min(900px, 100%);
        max-height: 94vh;
        overflow: auto;
        border-radius: 18px;
        border: 1px solid var(--divider-color);
        background: var(--card-background-color, #fff);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
      }
      .calendar-panel {
        margin: 4px 12px 12px;
        padding: 12px 0 0;
        border: 1px solid var(--divider-color);
        border-radius: 16px;
        background: rgba(127, 127, 127, 0.08);
        overflow: hidden;
      }
      .calendar-nav {
        display: grid;
        grid-template-columns: auto 1fr auto;
        align-items: center;
        gap: 8px;
        padding: 0 12px;
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
      .day-label {
        display: block;
        line-height: 1;
      }
      .day.blank {
        visibility: hidden;
        pointer-events: none;
      }
      .day.has-workout {
        border-color: var(--primary-color);
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
        font-weight: 700;
      }
      .day-markers {
        position: absolute;
        left: 50%;
        bottom: 4px;
        transform: translateX(-50%);
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 2px;
        min-width: 14px;
        min-height: 6px;
      }
      .day.selected {
        outline: 2px solid var(--card-background-color, #fff);
        outline-offset: -3px;
        box-shadow: 0 0 0 2px var(--primary-color);
      }
      .marker-dot {
        width: 4px;
        height: 4px;
        border-radius: 999px;
        background: currentColor;
        opacity: 0.95;
      }
      .selected-wrap {
        padding: 12px 12px 10px;
      }
      .selected-card .thumb-wrap {
        border-radius: 16px;
      }
      .workout-details {
        margin-top: 12px;
        display: grid;
        gap: 12px;
      }
      .detail-section {
        border: 1px solid var(--divider-color);
        border-radius: 14px;
        padding: 12px;
        background: rgba(127, 127, 127, 0.07);
      }
      .detail-title {
        margin-bottom: 10px;
        font-size: 0.82rem;
        font-weight: 700;
        color: var(--secondary-text-color);
        text-transform: uppercase;
        letter-spacing: 0.04em;
      }
      .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(118px, 1fr));
        gap: 8px;
      }
      .metric-tile {
        min-width: 0;
        padding: 10px;
        border-radius: 12px;
        background: var(--card-background-color, #fff);
      }
      .metric-label {
        color: var(--secondary-text-color);
        font-size: 0.75rem;
        line-height: 1.2;
      }
      .metric-value {
        margin-top: 4px;
        font-weight: 700;
        line-height: 1.25;
        overflow-wrap: anywhere;
      }
      .zone-bars {
        display: grid;
        gap: 8px;
      }
      .zone-bar {
        height: 14px;
        display: flex;
        overflow: hidden;
        border-radius: 999px;
        background: rgba(127, 127, 127, 0.16);
      }
      .zone-segment {
        min-width: 2px;
      }
      .zone-segment.hr-0 { background: #4cc9f0; }
      .zone-segment.hr-1 { background: #43aa8b; }
      .zone-segment.hr-2 { background: #f9c74f; }
      .zone-segment.hr-3 { background: #f9844a; }
      .zone-segment.hr-4 { background: #f94144; }
      .zone-segment.power-0 { background: #90be6d; }
      .zone-segment.power-1 { background: #43aa8b; }
      .zone-segment.power-2 { background: #577590; }
      .zone-segment.power-3 { background: #f8961e; }
      .zone-segment.power-4 { background: #f3722c; }
      .zone-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .zone-pill {
        padding: 3px 8px;
        border-radius: 999px;
        background: rgba(127, 127, 127, 0.13);
        font-size: 0.76rem;
      }
      .workout-strip {
        display: flex;
        gap: 8px;
        overflow-x: auto;
        padding: 10px 0 2px;
        scrollbar-width: thin;
      }
      .workout-tab {
        border: 1px solid var(--divider-color);
        border-radius: 8px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        min-width: 132px;
        max-width: 160px;
        padding: 0;
        overflow: hidden;
        text-align: left;
        cursor: pointer;
        font: inherit;
      }
      .workout-tab.selected {
        border-color: var(--primary-color);
        box-shadow: 0 0 0 1px var(--primary-color);
      }
      .workout-tab-thumb {
        width: 100%;
        aspect-ratio: 16 / 9;
        background: rgba(127, 127, 127, 0.14);
        overflow: hidden;
      }
      .workout-tab-thumb img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }
      .workout-tab-placeholder {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--secondary-text-color);
        font-size: 0.75rem;
      }
      .workout-tab-meta {
        padding: 6px 8px 7px;
        display: grid;
        gap: 2px;
      }
      .workout-tab-title {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 0.82rem;
        font-weight: 600;
      }
      .workout-tab-time {
        color: var(--secondary-text-color);
        font-size: 0.74rem;
      }
      @media (max-width: 520px) {
        .calendar-nav {
          grid-template-columns: auto 1fr auto;
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

    const renderedTitle = typeof this._config.title === "string" ? this._config.title.trim() : "";
    this._title.textContent = renderedTitle;
    this._title.style.display = renderedTitle ? "block" : "none";

    const entityId = this._resolvedEntityId();
    const stateObj = entityId ? this._hass.states[entityId] : null;

    this._ensureMediaArchiveLoaded(stateObj);

    const attributeWorkouts = stateObj ? this._extractWorkouts(stateObj) : [];
    const workouts = this._resolvedWorkouts(attributeWorkouts);
    const workoutsByDay = this._buildWorkoutsByDay(workouts);
    const currentIndex = this._clampedMainWorkoutIndex(workouts);

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

    const currentWorkout = workouts[currentIndex] || null;
    const latestHtml = currentWorkout
      ? this._renderWorkoutCard(currentWorkout, "latest-card-click", {
          showCalendarButton: true,
          calendarDisabled: !workouts.length,
          showWorkoutNavigation: workouts.length > 1,
          hasPreviousWorkout: currentIndex < workouts.length - 1,
          hasNextWorkout: currentIndex > 0,
        })
      : `<div class="state">${this._escape(this._config.empty_message)}</div>`;

    this._content.innerHTML = `
      ${latestHtml}
      ${
        !stateObj && !this._config.use_media_archive
          ? `<div class="state">Entity not found: ${this._escape(entityId || "image.<halthy_user>_workout")}</div>`
          : ""
      }
      ${
        this._config.use_media_archive && (this._mediaLoading || this._apiLoading)
          ? `<div class="state">Loading archived workouts...</div>`
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
        if (currentWorkout?.dayKey) {
          this._selectedDayKey = currentWorkout.dayKey;
          this._selectedWorkoutIndex = this._indexWithinDay(workoutsByDay, currentWorkout);
        }
        this._calendarOpen = true;
        this._render();
      });
    });

    this._content.querySelectorAll('[data-action="navigate-workout"]').forEach((navBtn) => {
      navBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const direction = navBtn.getAttribute("data-direction") || "";
        if (direction === "previous" && this._currentWorkoutIndex < workouts.length - 1) {
          this._currentWorkoutIndex += 1;
          this._render();
          return;
        }
        if (direction === "next" && this._currentWorkoutIndex > 0) {
          this._currentWorkoutIndex -= 1;
          this._render();
        }
      });
    });

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
        this._selectedWorkoutIndex = 0;
        this._render();
      });
    });

    this._content.querySelectorAll("[data-workout-index]").forEach((workoutBtn) => {
      workoutBtn.addEventListener("click", () => {
        const rawIndex = Number(workoutBtn.getAttribute("data-workout-index"));
        if (!Number.isInteger(rawIndex) || rawIndex < 0) {
          return;
        }
        this._selectedWorkoutIndex = rawIndex;
        this._render();
      });
    });

    const latestCard = this._content.querySelector(".latest-card-click");
    if (latestCard) {
      latestCard.addEventListener("click", (event) => {
        if (event.target && typeof event.target.closest === "function" && event.target.closest("[data-action]")) {
          return;
        }
        if (!workouts.length) {
          return;
        }
        if (currentWorkout?.dayKey) {
          this._selectedDayKey = currentWorkout.dayKey;
          this._selectedWorkoutIndex = this._indexWithinDay(workoutsByDay, currentWorkout);
        }
        this._calendarOpen = true;
        this._render();
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
    const title = this._betterWorkoutTitle(
      this._firstString(item.title, item.name),
      this._firstString(
        item.workout_type,
        item.workout_activity_type,
        item.activity_type,
        item.type
      )
    );

    const resolvedTitle = this._firstString(
      title,
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
      title: resolvedTitle,
      timestamp,
      dayKey: timestamp ? this._dayKey(timestamp) : "",
      dateLabel: timestamp ? this._formatDate(timestamp) : this._formatDate(dateSource),
      image,
      chips: this._chipsFromWorkout(item),
      details: this._workoutDetailsFromItem(item),
      entity_id: stateObj.entity_id,
      archiveKey: this._archiveKeyFromWorkoutItem(item, image),
      workoutId: this._workoutIdFromItem(item),
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
      details: this._workoutDetailsFromItem(attrs),
      entity_id: stateObj.entity_id,
      archiveKey: this._archiveKeyFromWorkoutItem(attrs, image),
      workoutId: this._workoutIdFromItem(attrs),
    };
  }

  _sortWorkouts(workouts) {
    return workouts.sort((a, b) => {
      const aTime = a.timestamp ? a.timestamp.getTime() : 0;
      const bTime = b.timestamp ? b.timestamp.getTime() : 0;
      return bTime - aTime;
    });
  }

  _resolvedWorkouts(attributeWorkouts) {
    const attributeList = Array.isArray(attributeWorkouts) ? attributeWorkouts : [];
    if (!this._config.use_media_archive) {
      return this._sortWorkouts([...attributeList]);
    }

    const merged = [...this._apiArchiveWorkouts, ...this._mediaWorkouts, ...attributeList];
    if (!merged.length) {
      return [];
    }

    const deduped = [];
    const identityIndexes = new Map();
    for (const workout of merged) {
      const identityKeys = this._workoutIdentityKeys(workout);
      const existingIndex = identityKeys
        .map((key) => identityIndexes.get(key))
        .find((index) => Number.isInteger(index));

      if (existingIndex === undefined) {
        const newIndex = deduped.length;
        deduped.push(workout);
        for (const key of identityKeys) {
          identityIndexes.set(key, newIndex);
        }
        continue;
      }

      const mergedWorkout = this._mergeWorkoutRecords(deduped[existingIndex], workout);
      deduped[existingIndex] = mergedWorkout;
      for (const key of [...identityKeys, ...this._workoutIdentityKeys(mergedWorkout)]) {
        identityIndexes.set(key, existingIndex);
      }
    }
    return this._sortWorkouts(deduped);
  }

  _workoutIdentityKeys(workout) {
    if (!workout || typeof workout !== "object") {
      return [`value:${String(workout)}`];
    }

    const keys = [];
    const workoutId = this._firstString(workout.workoutId).trim().toLowerCase();
    if (workoutId) {
      keys.push(`id:${workoutId}`);
    }

    const archiveKey = this._normalizeArchiveKey(
      this._firstString(
        workout.archiveKey,
        this._relativePathFromLocalUrl(workout.image),
        this._relativePathFromMediaSourceId(workout.image),
        this._relativePathFromWorkoutImageApiUrl(workout.image)
      )
    );
    if (archiveKey) {
      keys.push(`archive:${archiveKey}`);
    }

    const timestampIso =
      workout.timestamp instanceof Date && !Number.isNaN(workout.timestamp.getTime())
        ? workout.timestamp.toISOString()
        : "";
    if (!workoutId && !archiveKey && timestampIso) {
      keys.push(`time:${timestampIso}`);
    }

    if (keys.length) {
      return keys;
    }

    return [
      [
        "fallback",
        this._firstString(workout.dayKey),
        this._firstString(workout.image),
        this._firstString(workout.title),
      ].join(":"),
    ];
  }

  _mergeWorkoutRecords(existing, incoming) {
    const title = this._betterWorkoutTitle(existing.title, incoming.title);
    const timestamp = existing.timestamp || incoming.timestamp || null;
    const dayKey = this._firstString(existing.dayKey, incoming.dayKey);
    return {
      ...existing,
      ...incoming,
      title,
      timestamp,
      dayKey,
      dateLabel: this._firstString(existing.dateLabel, incoming.dateLabel),
      image: this._firstString(existing.image, incoming.image),
      chips: Array.isArray(existing.chips) && existing.chips.length ? existing.chips : incoming.chips || [],
      details: this._mergeWorkoutDetails(existing.details, incoming.details),
      entity_id: this._firstString(existing.entity_id, incoming.entity_id),
      archiveKey: this._firstString(existing.archiveKey, incoming.archiveKey),
      workoutId: this._firstString(existing.workoutId, incoming.workoutId),
    };
  }

  _mergeWorkoutDetails(existing, incoming) {
    const existingDetails = existing && typeof existing === "object" ? existing : {};
    const incomingDetails = incoming && typeof incoming === "object" ? incoming : {};
    return {
      ...incomingDetails,
      ...existingDetails,
      summary: this._mergeMetricLists(existingDetails.summary, incomingDetails.summary),
      heart: this._mergeMetricLists(existingDetails.heart, incomingDetails.heart),
      speed: this._mergeMetricLists(existingDetails.speed, incomingDetails.speed),
      elevation: this._mergeMetricLists(existingDetails.elevation, incomingDetails.elevation),
      speedRange: existingDetails.speedRange || incomingDetails.speedRange || null,
      heartZones: Array.isArray(existingDetails.heartZones) && existingDetails.heartZones.length
        ? existingDetails.heartZones
        : incomingDetails.heartZones || [],
      powerZones: Array.isArray(existingDetails.powerZones) && existingDetails.powerZones.length
        ? existingDetails.powerZones
        : incomingDetails.powerZones || [],
      hasData: Boolean(existingDetails.hasData || incomingDetails.hasData),
    };
  }

  _mergeMetricLists(existing, incoming) {
    const merged = new Map();
    for (const metric of [...(incoming || []), ...(existing || [])]) {
      if (!metric || !metric.label || !metric.value) {
        continue;
      }
      merged.set(metric.label, metric);
    }
    return [...merged.values()];
  }

  _betterWorkoutTitle(existingTitle, incomingTitle) {
    const existing = this._firstString(existingTitle);
    const incoming = this._firstString(incomingTitle);
    if (this._isGenericWorkoutTitle(existing) && !this._isGenericWorkoutTitle(incoming)) {
      return incoming;
    }
    if (!this._isGenericWorkoutTitle(existing)) {
      return existing;
    }
    return incoming || existing || "Workout";
  }

  _isGenericWorkoutTitle(title) {
    const normalized = this._firstString(title).trim().toLowerCase();
    return !normalized || normalized === "workout";
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

  _clampedMainWorkoutIndex(workouts) {
    const count = Array.isArray(workouts) ? workouts.length : 0;
    if (count <= 0) {
      this._currentWorkoutIndex = 0;
      return 0;
    }
    if (!Number.isInteger(this._currentWorkoutIndex) || this._currentWorkoutIndex < 0) {
      this._currentWorkoutIndex = 0;
      return 0;
    }
    if (this._currentWorkoutIndex >= count) {
      this._currentWorkoutIndex = count - 1;
    }
    return this._currentWorkoutIndex;
  }

  _indexWithinDay(workoutsByDay, workout) {
    if (!workout?.dayKey || !workoutsByDay || typeof workoutsByDay.get !== "function") {
      return 0;
    }
    const dayWorkouts = workoutsByDay.get(workout.dayKey) || [];
    const index = dayWorkouts.indexOf(workout);
    return index >= 0 ? index : 0;
  }

  _renderWorkoutCard(workout, extraClass = "", options = {}) {
    const imageHtml = workout.image
      ? `<img class="thumb" loading="lazy" src="${this._escapeAttr(workout.image)}" alt="${this._escapeAttr(
          workout.title || "Workout"
        )}" />`
      : `<div class="placeholder">WK</div>`;
    const showWorkoutNavigation = options.showWorkoutNavigation === true;
    const navHtml = showWorkoutNavigation
      ? `
        ${
          options.hasPreviousWorkout
            ? `<button
                class="workout-nav-btn left"
                data-action="navigate-workout"
                data-direction="previous"
                aria-label="Show previous workout"
                title="Show previous workout"
              >
                <ha-icon icon="mdi:chevron-left"></ha-icon>
              </button>`
            : ""
        }
        ${
          options.hasNextWorkout
            ? `<button
                class="workout-nav-btn right"
                data-action="navigate-workout"
                data-direction="next"
                aria-label="Show newer workout"
                title="Show newer workout"
              >
                <ha-icon icon="mdi:chevron-right"></ha-icon>
              </button>`
            : ""
        }
      `
      : "";

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
          <ha-icon class="calendar-inline-icon" icon="${this._escapeAttr(this._calendarIcon())}"></ha-icon>
        </button>`
      : "";
    const headlineHtml = `
      <div class="headline-row">
        <div class="headline-main">
          <div class="name">${this._escape(workout.title || "Workout")}</div>
          ${workout.dateLabel ? `<div class="date">${this._escape(workout.dateLabel)}</div>` : ""}
        </div>
        ${calendarButtonHtml}
      </div>
    `;

    return `
      <article class="workout-card ${this._escapeAttr(extraClass)}">
        <div class="thumb-wrap">${imageHtml}${navHtml}</div>
        <div class="meta">
          ${headlineHtml}
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
    const selectedIndex = this._clampedWorkoutIndex(selectedWorkouts);
    const selectedWorkout = selectedWorkouts[selectedIndex] || null;
    const selectedMessage = this._config.calendar_empty_day_message;
    const selectorHtml =
      selectedWorkouts.length > 1 ? this._renderWorkoutSelector(selectedWorkouts, selectedIndex) : "";

    const selectedHtml = selectedWorkout
      ? `
        ${this._renderWorkoutCard(selectedWorkout, "selected-card")}
        ${this._renderWorkoutDetails(selectedWorkout)}
        ${selectorHtml}
      `
      : `<div class="state">${this._escape(selectedMessage)}</div>`;

    return `
      <div class="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true" aria-label="Workout Calendar">
          <div class="selected-wrap">${selectedHtml}</div>
          <div class="calendar-panel">
            <div class="calendar-nav">
              <button class="icon-btn" data-action="prev-month" aria-label="Previous month">&#8249;</button>
              <div class="month-label">${this._escape(monthLabel)}</div>
              <button class="icon-btn" data-action="next-month" aria-label="Next month">&#8250;</button>
            </div>
            <div class="weekdays">${weekdayHtml}</div>
            <div class="days-grid">${calendarGrid}</div>
          </div>
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
          <span class="day-label">${day}</span>
          ${this._renderDayMarkers(count)}
        </button>
      `);
    }

    while (cells.length % 7 !== 0) {
      cells.push('<button class="day blank" disabled aria-hidden="true"></button>');
    }

    return cells.join("");
  }

  _renderDayMarkers(count) {
    if (!Number.isFinite(count) || count <= 0) {
      return "";
    }
    const dots = Array.from({ length: Math.min(count, 4) }, () => '<span class="marker-dot"></span>').join("");
    return `<span class="day-markers">${dots}</span>`;
  }

  _renderWorkoutSelector(workouts, selectedIndex) {
    return `
      <div class="workout-strip" role="list" aria-label="Workouts on selected day">
        ${workouts
          .map((workout, index) => this._renderWorkoutSelectorItem(workout, index, index === selectedIndex))
          .join("")}
      </div>
    `;
  }

  _renderWorkoutSelectorItem(workout, index, selected) {
    const imageHtml = workout.image
      ? `<img src="${this._escapeAttr(workout.image)}" alt="${this._escapeAttr(workout.title || "Workout")}" loading="lazy" />`
      : `<div class="workout-tab-placeholder">No image</div>`;
    const timeLabel = this._formatTime(workout.timestamp) || workout.dateLabel || "";
    return `
      <button
        class="workout-tab ${selected ? "selected" : ""}"
        data-workout-index="${index}"
        aria-label="${this._escapeAttr(workout.title || "Workout")}${timeLabel ? ` ${this._escapeAttr(timeLabel)}` : ""}"
        ${selected ? 'aria-current="true"' : ""}
      >
        <div class="workout-tab-thumb">${imageHtml}</div>
        <div class="workout-tab-meta">
          <div class="workout-tab-title">${this._escape(workout.title || "Workout")}</div>
          ${timeLabel ? `<div class="workout-tab-time">${this._escape(timeLabel)}</div>` : ""}
        </div>
      </button>
    `;
  }

  _renderWorkoutDetails(workout) {
    const details = workout?.details && typeof workout.details === "object" ? workout.details : null;
    if (!details || !details.hasData) {
      return `
        <div class="workout-details">
          <div class="detail-section">
            <div class="detail-title">Workout details</div>
            <div class="state">No detailed workout metadata is available for this archived workout.</div>
          </div>
        </div>
      `;
    }

    const sections = [
      this._renderMetricSection("Elevation & environment", details.elevation),
      this._renderZoneSection("Heart-rate zones", details.heartZones, "hr"),
      this._renderZoneSection("Power zones", details.powerZones, "power"),
    ].filter(Boolean);

    if (!sections.length) {
      return "";
    }

    return `<div class="workout-details">${sections.join("")}</div>`;
  }

  _renderMetricSection(title, metrics) {
    const visibleMetrics = Array.isArray(metrics)
      ? metrics.filter((metric) => metric && metric.label && metric.value)
      : [];
    if (!visibleMetrics.length) {
      return "";
    }

    return `
      <section class="detail-section">
        <div class="detail-title">${this._escape(title)}</div>
        <div class="metric-grid">
          ${visibleMetrics.map((metric) => this._renderMetricTile(metric)).join("")}
        </div>
      </section>
    `;
  }

  _renderMetricTile(metric) {
    return `
      <div class="metric-tile">
        <div class="metric-label">${this._escape(metric.label)}</div>
        <div class="metric-value">${this._escape(metric.value)}</div>
      </div>
    `;
  }

  _renderZoneSection(title, zones, classPrefix) {
    const normalizedZones = this._normalizedZones(zones);
    if (!normalizedZones.length) {
      return "";
    }

    const totalDuration = normalizedZones.reduce((sum, zone) => sum + zone.duration, 0);
    if (totalDuration <= 0) {
      return "";
    }

    return `
      <section class="detail-section">
        <div class="detail-title">${this._escape(title)}</div>
        <div class="zone-bars">
          <div class="zone-bar">
            ${normalizedZones
              .map((zone, index) => {
                const width = Math.max(2, (zone.duration / totalDuration) * 100);
                return `<span class="zone-segment ${classPrefix}-${index % 5}" style="width: ${width.toFixed(2)}%;"></span>`;
              })
              .join("")}
          </div>
          <div class="zone-legend">
            ${normalizedZones
              .map(
                (zone) =>
                  `<span class="zone-pill">${this._escape(zone.label)} ${this._escape(
                    this._formatShortDuration(zone.duration)
                  )}</span>`
              )
              .join("")}
          </div>
        </div>
      </section>
    `;
  }

  _clampedWorkoutIndex(workouts) {
    const count = Array.isArray(workouts) ? workouts.length : 0;
    if (count <= 0) {
      return 0;
    }
    if (!Number.isInteger(this._selectedWorkoutIndex) || this._selectedWorkoutIndex < 0) {
      this._selectedWorkoutIndex = 0;
      return 0;
    }
    if (this._selectedWorkoutIndex >= count) {
      this._selectedWorkoutIndex = count - 1;
    }
    return this._selectedWorkoutIndex;
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

    const heartRateZone = this._dominantZoneChip(item.heart_rate_zones, "HR");
    if (heartRateZone) {
      chips.push(heartRateZone);
    }

    const powerZone = this._dominantZoneChip(item.cycling_power_zones, "Power");
    if (powerZone) {
      chips.push(powerZone);
    }

    chips.push(...this._weatherChipsFromWorkout(item));

    return chips;
  }

  _workoutDetailsFromItem(item) {
    if (!item || typeof item !== "object") {
      return { hasData: false };
    }

    const distanceM = this._toNumber(item.workout_distance_m ?? item.distance_m ?? item.distance);
    const durationS = this._toNumber(
      item.workout_duration_s ?? item.duration_s ?? item.duration_seconds ?? item.duration
    );
    const activeEnergyKcal = this._toNumber(
      item.workout_active_energy_kcal ?? item.active_energy_kcal ?? item.energy_kcal
    );
    const flights = this._toNumber(
      item.total_flights_climbed ?? item.workout_total_flights_climbed ?? item.flights_climbed ?? item.flights
    );
    const avgHeartRate = this._toNumber(item.workout_avg_heart_rate_bpm ?? item.avg_heart_rate_bpm);
    const minHeartRate = this._toNumber(item.lowest_heart_rate_bpm ?? item.min_heart_rate_bpm);
    const maxHeartRate = this._toNumber(item.highest_heart_rate_bpm ?? item.max_heart_rate_bpm);
    const respiratoryRate = this._toNumber(
      item.respiratory_rate_brpm ?? item.avg_respiratory_rate_brpm ?? item.respiratory_rate
    );
    const powerW = this._toNumber(item.power_w ?? item.avg_power_w ?? item.power);
    const avgSpeedMps =
      this._toNumber(item.avg_speed_mps ?? item.workout_avg_speed_mps ?? item.average_speed_mps) ??
      (distanceM !== null && durationS !== null && distanceM > 0 && durationS > 0 ? distanceM / durationS : null);
    const minSpeedMps = this._toNumber(item.lowest_speed_mps ?? item.min_speed_mps ?? item.lowest_speed);
    const maxSpeedMps = this._toNumber(item.highest_speed_mps ?? item.max_speed_mps ?? item.highest_speed);
    const cadenceSpm = this._toNumber(item.cadence_spm ?? item.avg_cadence_spm ?? item.cadence);
    const elevationGainM = this._toNumber(item.workout_elevation_gain_m ?? item.elevation_gain_m);
    const highestAltitudeM = this._toNumber(item.highest_altitude_m ?? item.max_altitude_m ?? item.highest_altitude);
    const lowestAltitudeM = this._toNumber(item.lowest_altitude_m ?? item.min_altitude_m ?? item.lowest_altitude);
    const temperatureC = this._toNumber(
      item.weather_temperature_c ?? item.weather_temperature_celsius ?? item.temperature_c ?? item.temperature_celsius
    );
    const humidityPercent = this._toNumber(
      item.weather_humidity_percent ?? item.humidity_percent ?? item.weather_humidity
    );
    const weatherCondition = this._firstString(
      item.weather_condition,
      this._weatherConditionName(this._toNumber(item.weather_condition_raw))
    );

    const speedRangeMetrics = [
      this._metric("Lowest", this._formatSpeed(minSpeedMps)),
      this._metric("Average", this._formatSpeed(avgSpeedMps)),
      this._metric("Highest", this._formatSpeed(maxSpeedMps)),
    ].filter(Boolean);

    const summary = [
      this._metric("Duration", this._formatDuration(durationS)),
      this._metric("Distance", this._formatDistance(distanceM)),
      this._metric("Active energy", this._formatRoundedUnit(activeEnergyKcal, "kcal")),
      this._metric("Flights climbed", this._formatRoundedUnit(flights, "floors")),
    ].filter(Boolean);

    const heart = [
      this._metric("Avg heart rate", this._formatRoundedUnit(avgHeartRate, "bpm")),
      this._metric("Lowest heart rate", this._formatRoundedUnit(minHeartRate, "bpm")),
      this._metric("Highest heart rate", this._formatRoundedUnit(maxHeartRate, "bpm")),
      this._metric("Respiratory rate", this._formatRoundedUnit(respiratoryRate, "br/min")),
      this._metric("Power", this._formatRoundedUnit(powerW, "W")),
    ].filter(Boolean);

    const speed = [
      this._metric("Average speed", this._formatSpeed(avgSpeedMps)),
      this._metric("Highest speed", this._formatSpeed(maxSpeedMps)),
      this._metric("Lowest speed", this._formatSpeed(minSpeedMps)),
      this._metric("Cadence", this._formatRoundedUnit(cadenceSpm, "spm")),
    ].filter(Boolean);

    const elevation = [
      this._metric("Elevation gain", this._formatRoundedUnit(elevationGainM, "m")),
      this._metric("Highest altitude", this._formatRoundedUnit(highestAltitudeM, "m")),
      this._metric("Lowest altitude", this._formatRoundedUnit(lowestAltitudeM, "m")),
      this._metric("Weather", weatherCondition),
      this._metric("Temperature", this._formatTemperature(temperatureC)),
      this._metric("Humidity", this._formatPercent(humidityPercent)),
    ].filter(Boolean);

    const heartZones = this._firstArray(item.heart_rate_zones, item.workout_heart_rate_zones);
    const powerZones = this._firstArray(item.cycling_power_zones, item.power_zones, item.workout_power_zones);
    const hasData = Boolean(
      summary.length ||
        heart.length ||
        speed.length ||
        elevation.length ||
        this._normalizedZones(heartZones).length ||
        this._normalizedZones(powerZones).length
    );

    return {
      summary,
      heart,
      speed,
      elevation,
      speedRange: speedRangeMetrics.length
        ? {
            metrics: speedRangeMetrics,
            labels: new Set(["Lowest speed", "Average speed", "Highest speed"]),
          }
        : null,
      heartZones,
      powerZones,
      hasData,
    };
  }

  _metric(label, value) {
    const normalized = typeof value === "string" ? value.trim() : "";
    if (!normalized) {
      return null;
    }
    return { label, value: normalized };
  }

  _firstArray(...values) {
    for (const value of values) {
      if (Array.isArray(value) && value.length) {
        return value;
      }
    }
    return [];
  }

  _normalizedZones(zones) {
    if (!Array.isArray(zones)) {
      return [];
    }
    return zones
      .map((zone, index) => {
        if (!zone || typeof zone !== "object") {
          return null;
        }
        const duration = this._toNumber(zone.duration_s ?? zone.durationSeconds ?? zone.duration);
        if (duration === null || duration <= 0) {
          return null;
        }
        const zoneNumber = this._toNumber(zone.zone ?? zone.index ?? zone.zoneIndex);
        const label = zoneNumber !== null ? `Z${Math.round(zoneNumber)}` : `Z${index + 1}`;
        return { label, duration };
      })
      .filter(Boolean);
  }

  _weatherChipsFromWorkout(item) {
    if (!item || typeof item !== "object") {
      return [];
    }

    const chips = [];
    const condition = this._firstString(
      item.weather_condition,
      this._weatherConditionName(this._toNumber(item.weather_condition_raw))
    );
    if (condition) {
      chips.push(condition);
    }

    const temperatureC = this._toNumber(
      item.weather_temperature_c ??
        item.weather_temperature_celsius ??
        item.temperature_c ??
        item.temperature_celsius
    );
    if (temperatureC !== null) {
      chips.push(`${Math.round(temperatureC)} °C`);
    }

    const humidityPercent = this._toNumber(
      item.weather_humidity_percent ??
        item.humidity_percent ??
        item.weather_humidity
    );
    if (humidityPercent !== null) {
      const normalizedHumidity = humidityPercent <= 1 ? humidityPercent * 100 : humidityPercent;
      chips.push(`${Math.round(Math.max(0, Math.min(100, normalizedHumidity)))}% humidity`);
    }

    return chips;
  }

  _weatherConditionName(rawValue) {
    if (rawValue === null) {
      return "";
    }
    const names = {
      1: "Clear",
      2: "Fair",
      3: "Partly cloudy",
      4: "Mostly cloudy",
      5: "Cloudy",
      6: "Foggy",
      7: "Haze",
      8: "Windy",
      9: "Blustery",
      10: "Smoky",
      11: "Dust",
      12: "Snow",
      13: "Hail",
      14: "Sleet",
      15: "Freezing drizzle",
      16: "Freezing rain",
      17: "Rain and hail",
      18: "Rain and snow",
      19: "Rain and sleet",
      20: "Snow and sleet",
      21: "Drizzle",
      22: "Scattered showers",
      23: "Showers",
      24: "Thunderstorms",
      25: "Tropical storm",
      26: "Hurricane",
      27: "Tornado",
    };
    return names[Math.round(rawValue)] || "";
  }

  _dominantZoneChip(zones, label) {
    if (!Array.isArray(zones) || !zones.length) {
      return "";
    }

    let bestZone = null;
    let bestDuration = 0;
    for (const zone of zones) {
      if (!zone || typeof zone !== "object") {
        continue;
      }
      const duration = this._toNumber(zone.duration_s);
      if (duration !== null && duration > bestDuration) {
        bestDuration = duration;
        bestZone = zone;
      }
    }

    if (!bestZone || bestDuration <= 0) {
      return "";
    }

    const zoneNumber = this._toNumber(bestZone.zone);
    const zoneLabel = zoneNumber !== null ? `Z${Math.round(zoneNumber)}` : "Zone";
    return `${label} ${zoneLabel} ${this._formatShortDuration(bestDuration)}`;
  }

  _formatShortDuration(seconds) {
    const minutes = Math.max(1, Math.round(seconds / 60));
    if (minutes < 60) {
      return `${minutes}m`;
    }
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;
    return remainder > 0 ? `${hours}h ${remainder}m` : `${hours}h`;
  }

  _ensureMediaArchiveLoaded(stateObj) {
    if (!this._config.use_media_archive || !this._hass) {
      return;
    }

    const attrs = stateObj?.attributes || {};
    this._ensureArchiveApiLoaded(stateObj, attrs);
    if (typeof this._hass.callWS !== "function") {
      return;
    }

    const folders = this._archiveFolderCandidates(attrs);
    if (!folders.length) {
      return;
    }

    const archiveFileName = this._firstString(attrs.archive_file_name);
    const foldersKey = folders.join("|");
    const folderChanged = foldersKey !== this._mediaArchiveFoldersKey;
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

    this._mediaArchiveFoldersKey = foldersKey;
    const resolvedEntityId = stateObj?.entity_id || this._resolvedEntityId() || _entityFromUser(this._config?.user || "");
    void this._loadMediaArchiveWorkouts(folders, resolvedEntityId);
  }

  _defaultArchiveFolderForUser() {
    const userFromConfig = _sanitizeIdentifier(this._config?.user || "");
    const userFromEntity = _userFromWorkoutEntity(this._resolvedEntityId());
    const user = userFromConfig || userFromEntity;
    if (!user) {
      return "";
    }
    return `halthy/workouts/${user}`;
  }

  _ensureArchiveApiLoaded(stateObj, attrs = {}) {
    if (!this._config.use_media_archive) {
      return;
    }

    const resolvedEntityId = stateObj?.entity_id || this._resolvedEntityId() || _entityFromUser(this._config?.user || "");
    const user = this._firstString(
      _sanitizeIdentifier(this._config?.user || ""),
      _userFromWorkoutEntity(resolvedEntityId),
      _sanitizeIdentifier(this._firstString(attrs.username))
    );
    if (!user) {
      return;
    }

    const archiveFileName = this._firstString(attrs.archive_file_name);
    const hasNewLatestFile = !!archiveFileName && archiveFileName !== this._lastArchiveFileName;
    if (archiveFileName) {
      this._lastArchiveFileName = archiveFileName;
    }
    const userChanged = user !== this._apiArchiveUser;
    if (!userChanged && !hasNewLatestFile && (this._apiLoading || this._apiWorkoutsLoaded)) {
      return;
    }

    this._apiArchiveUser = user;
    void this._loadArchiveApiWorkouts(user, resolvedEntityId);
  }

  async _loadArchiveApiWorkouts(user, entityId) {
    const loadSeq = ++this._apiLoadSeq;
    this._apiLoading = true;
    this._apiWorkoutsLoaded = false;
    this._render();

    try {
      const endpoint = `/api/halthy/workouts?username=${encodeURIComponent(user)}&limit=300`;
      const payload = await this._fetchAuthedJson(endpoint);
      const records = Array.isArray(payload?.workouts) ? payload.workouts : [];
      const workouts = (
        await Promise.all(records.map((record) => this._workoutFromArchiveApiItemAsync(record, entityId)))
      ).filter((item) => item !== null);

      this._sortWorkouts(workouts);
      if (loadSeq !== this._apiLoadSeq) {
        return;
      }
      this._apiArchiveWorkouts = workouts;
    } catch (_error) {
      if (loadSeq !== this._apiLoadSeq) {
        return;
      }
      this._apiArchiveWorkouts = [];
    } finally {
      if (loadSeq !== this._apiLoadSeq) {
        return;
      }
      this._apiLoading = false;
      this._apiWorkoutsLoaded = true;
      this._render();
    }
  }

  async _fetchAuthedJson(url) {
    if (this._hass && typeof this._hass.callApi === "function") {
      const normalizedPath = typeof url === "string" ? url.trim() : "";
      if (normalizedPath.startsWith("/api/")) {
        const apiPath = normalizedPath.slice(5);
        if (apiPath) {
          try {
            return await this._hass.callApi("get", apiPath);
          } catch (_error) {
            // Fall through to fetch-based fallback below.
          }
        }
      }
    }

    const absoluteUrl = this._sameOriginAbsoluteUrl(url);
    if (!absoluteUrl || typeof fetch !== "function") {
      return null;
    }

    const token = this._frontendAuthToken();
    const optionsWithAuth = {
      method: "GET",
      headers: token ? { Authorization: `Bearer ${token}`, Accept: "application/json" } : { Accept: "application/json" },
      credentials: "same-origin",
    };

    let response;
    try {
      response = await fetch(absoluteUrl.toString(), optionsWithAuth);
      if (!response.ok && token) {
        response = await fetch(absoluteUrl.toString(), {
          method: "GET",
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
      }
    } catch (_error) {
      return null;
    }

    if (!response || !response.ok) {
      return null;
    }
    try {
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  async _workoutFromArchiveApiItemAsync(record, entityId) {
    if (!record || typeof record !== "object") {
      return null;
    }

    const relativePath = this._firstString(record.relative_path);
    const fileName = this._firstString(record.file_name, relativePath ? relativePath.split("/").pop() || "" : "");
    const dateInfoFromName = this._archiveDateInfoFromFileName(fileName);
    const timestamp = this._toDate(this._firstString(record.timestamp)) || dateInfoFromName?.timestamp;
    const dayKey =
      this._firstString(record.day_key) || dateInfoFromName?.dayKey || (timestamp ? this._dayKey(timestamp) : "");
    const dateLabel = timestamp ? this._formatDate(timestamp) : "";

    const imageApiUrl = this._firstString(record.image_url);
    const localUrlFromRecord = this._firstString(record.local_url);
    const fallbackLocalUrl = relativePath
      ? `/media/local/${relativePath
          .split("/")
          .filter((segment) => segment.length > 0)
          .map((segment) => encodeURIComponent(segment))
          .join("/")}`
      : "";
    const mediaSourceId = this._firstString(record.media_source_id);
    const resolvedImage = imageApiUrl
      ? this._normalizeImageUrl(imageApiUrl)
      : await this._authSafeImageUrl(
          this._normalizeImageUrl(this._firstString(localUrlFromRecord, fallbackLocalUrl, mediaSourceId))
        );
    if (!resolvedImage && !dayKey && !timestamp) {
      return null;
    }

    return {
      title: this._firstString(
        record.workout_type,
        record.workout_activity_type,
        record.activity_type,
        record.workout_kind,
        record.type,
        record.title,
        record.name,
        "Workout"
      ),
      timestamp,
      dayKey,
      dateLabel,
      image: resolvedImage,
      chips: this._chipsFromWorkout(record),
      details: this._workoutDetailsFromItem(record),
      entity_id: entityId,
      archiveKey: relativePath,
      workoutId: this._workoutIdFromItem(record),
    };
  }

  _archiveFolderCandidates(attrs = {}) {
    const unique = new Set();
    const folders = [];

    const addFolder = (candidate) => {
      if (typeof candidate !== "string") {
        return;
      }
      const normalized = candidate.replace(/^\/+/, "").replace(/\/+$/, "").trim();
      if (!normalized || unique.has(normalized)) {
        return;
      }
      unique.add(normalized);
      folders.push(normalized);
    };

    const detectedFolder = this._detectArchiveFolder(attrs);
    if (detectedFolder) {
      addFolder(detectedFolder);
    }

    const defaultFolder = this._defaultArchiveFolderForUser();
    if (defaultFolder) {
      addFolder(defaultFolder);
    }

    const userCandidates = [
      _sanitizeIdentifier(this._config?.user || ""),
      _userFromWorkoutEntity(this._resolvedEntityId()),
      _sanitizeIdentifier(this._firstString(attrs.username)),
    ].filter((item) => !!item);

    const domainCandidates = ["halthy", "halthy_bridge", "health2ha", "health2ha_bridge"];
    for (const user of userCandidates) {
      for (const domain of domainCandidates) {
        addFolder(`${domain}/workouts/${user}`);
      }
    }

    return folders;
  }

  async _loadMediaArchiveWorkouts(folderOrFolders, entityId) {
    const loadSeq = ++this._mediaLoadSeq;
    this._mediaLoading = true;
    this._mediaWorkoutsLoaded = false;
    this._render();

    try {
      const folderCandidates = Array.isArray(folderOrFolders)
        ? folderOrFolders.filter((folder) => typeof folder === "string" && folder.trim())
        : [folderOrFolders].filter((folder) => typeof folder === "string" && folder.trim());

      const imageChildren = [];
      const seenChildren = new Set();
      for (const folder of folderCandidates) {
        const mediaContentId = `media-source://media_source/local/${folder}`;
        const children = await this._collectImageMediaChildren(mediaContentId);
        for (const child of children) {
          const childKey = this._firstString(
            child?.media_content_id,
            child?.url,
            child?.thumbnail,
            child?.title
          );
          const normalizedKey = childKey || JSON.stringify(child || {});
          if (seenChildren.has(normalizedKey)) {
            continue;
          }
          seenChildren.add(normalizedKey);
          imageChildren.push(child);
        }
      }

      const workouts = (
        await Promise.all(
          imageChildren.map((child) => this._workoutFromMediaChildAsync(child, entityId))
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

  async _collectImageMediaChildren(mediaContentId, depth = 0, visited = new Set()) {
    if (!mediaContentId || typeof mediaContentId !== "string") {
      return [];
    }
    if (visited.has(mediaContentId)) {
      return [];
    }
    visited.add(mediaContentId);

    let response;
    try {
      response = await this._hass.callWS({
        type: "media_source/browse_media",
        media_content_id: mediaContentId,
      });
    } catch (_error) {
      return [];
    }

    const children = Array.isArray(response?.children) ? response.children : [];
    const images = [];
    for (const child of children) {
      const isImageChild = this._isImageMediaChild(child);
      if (isImageChild) {
        images.push(child);
      }

      const childMediaContentId = this._firstString(child?.media_content_id);
      const canExpand =
        child &&
        typeof child === "object" &&
        !isImageChild &&
        child.can_expand !== false;
      if (!canExpand || !childMediaContentId || depth >= 6) {
        continue;
      }
      const nested = await this._collectImageMediaChildren(childMediaContentId, depth + 1, visited);
      if (nested.length) {
        images.push(...nested);
      }
    }

    return images;
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
    const candidate = this._firstString(child.title, child.media_content_id, child.url, child.thumbnail);
    return /\.(png|jpe?g|webp|gif|bmp|svg|tiff?|heic|heif|avif)(\?|$)/i.test(candidate);
  }

  async _workoutFromMediaChildAsync(child, entityId) {
    const mediaSourceId = this._firstString(child.media_content_id);
    const relativePathFromMediaSource = this._relativePathFromMediaSourceId(mediaSourceId);
    const relativePathFromUrl = this._relativePathFromLocalUrl(this._firstString(child.url, child.thumbnail));
    const relativePath = relativePathFromMediaSource || relativePathFromUrl;
    const fileName = relativePath
      ? relativePath.split("/").pop() || ""
      : this._firstString(child.title, mediaSourceId, child.url, child.thumbnail);
    const fileNameDateInfo =
      this._archiveDateInfoFromFileName(fileName) ||
      this._archiveDateInfoFromFileName(this._firstString(child.title));
    const timestamp =
      fileNameDateInfo?.timestamp ||
      this._toDate(child.modified_at) ||
      this._toDate(child.created_at);

    const dateLabel = timestamp ? this._formatDate(timestamp) : "";
    const dayKey = fileNameDateInfo?.dayKey || (timestamp ? this._dayKey(timestamp) : "");

    const resolvedImage = await this._resolvedMediaImageUrl(child, mediaSourceId, relativePath);
    if (!resolvedImage && !dayKey && !timestamp) {
      return null;
    }

    return {
      title: "Workout",
      timestamp,
      dayKey,
      dateLabel,
      image: resolvedImage,
      chips: [],
      details: this._workoutDetailsFromItem(child),
      entity_id: entityId,
      archiveKey: relativePath,
      workoutId: this._workoutIdFromItem(child),
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

    if (relativePath) {
      return await this._authSafeImageUrl(this._normalizeImageUrl(`/media/local/${relativePath}`));
    }
    return null;
  }

  _isProtectedMediaLocalUrl(url) {
    const absoluteUrl = this._sameOriginAbsoluteUrl(url);
    return !!absoluteUrl && absoluteUrl.pathname.startsWith("/media/local/");
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

    const absoluteUrl = this._sameOriginAbsoluteUrl(normalized);
    const token = this._frontendAuthToken();
    if (!absoluteUrl || typeof fetch !== "function") {
      return normalized;
    }

    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
      const response = await fetch(absoluteUrl.toString(), {
        method: "GET",
        headers,
        credentials: "same-origin",
      });
      if (!response.ok) {
        return normalized;
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      this._imageObjectUrls.add(objectUrl);
      return objectUrl;
    } catch (_error) {
      return normalized;
    }
  }

  _frontendAuthToken() {
    const direct = this._firstString(this._hass?.auth?.data?.access_token);
    if (direct) {
      return direct;
    }
    return this._firstString(
      this._hass?.connection?.options?.auth?.accessToken,
      this._hass?.connection?.options?.auth?.data?.access_token
    );
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

  _sameOriginAbsoluteUrl(url) {
    if (!url || typeof url !== "string") {
      return null;
    }

    const baseHref =
      typeof window !== "undefined" && window.location?.href
        ? window.location.href
        : "http://localhost/";
    const allowedOrigins = new Set();
    if (typeof window !== "undefined" && window.location?.origin) {
      allowedOrigins.add(window.location.origin);
    }

    if (this._hass && typeof this._hass.hassUrl === "function") {
      try {
        allowedOrigins.add(new URL(this._hass.hassUrl("/"), baseHref).origin);
      } catch (_error) {
        // If Home Assistant cannot provide a base URL, fall back to window origin only.
      }
    }

    try {
      const absoluteUrl = new URL(this._absoluteUrl(url), baseHref);
      return allowedOrigins.has(absoluteUrl.origin) ? absoluteUrl : null;
    } catch (_error) {
      return null;
    }
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
    const info = this._archiveDateInfoFromFileName(fileName);
    return info ? info.timestamp : null;
  }

  _archiveDateInfoFromFileName(fileName) {
    const source = typeof fileName === "string" ? fileName.trim() : "";
    if (!source) {
      return null;
    }

    const compactDateTime = /(\d{8})T(\d{6})Z?/i.exec(source);
    if (compactDateTime) {
      const dateToken = compactDateTime[1];
      const timeToken = compactDateTime[2];
      const year = Number(dateToken.slice(0, 4));
      const month = Number(dateToken.slice(4, 6));
      const day = Number(dateToken.slice(6, 8));
      const parsed = this._utcDateFromParts(
        year,
        month,
        day,
        Number(timeToken.slice(0, 2)),
        Number(timeToken.slice(2, 4)),
        Number(timeToken.slice(4, 6))
      );
      if (parsed) {
        return {
          timestamp: parsed,
          dayKey: this._dayKeyFromParts(year, month, day),
        };
      }
    }

    const separatedDateTime = /(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})[T _-]?(\d{2})[:._-]?(\d{2})(?:[:._-]?(\d{2}))?/.exec(
      source
    );
    if (separatedDateTime) {
      const year = Number(separatedDateTime[1]);
      const month = Number(separatedDateTime[2]);
      const day = Number(separatedDateTime[3]);
      const parsed = this._utcDateFromParts(
        year,
        month,
        day,
        Number(separatedDateTime[4]),
        Number(separatedDateTime[5]),
        Number(separatedDateTime[6] || "0")
      );
      if (parsed) {
        return {
          timestamp: parsed,
          dayKey: this._dayKeyFromParts(year, month, day),
        };
      }
    }

    const dateOnly = /(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})/.exec(source);
    if (dateOnly) {
      const year = Number(dateOnly[1]);
      const month = Number(dateOnly[2]);
      const day = Number(dateOnly[3]);
      const parsed = this._utcDateFromParts(
        year,
        month,
        day,
        0,
        0,
        0
      );
      if (parsed) {
        return {
          timestamp: parsed,
          dayKey: this._dayKeyFromParts(year, month, day),
        };
      }
    }

    return null;
  }

  _utcDateFromParts(year, month, day, hour, minute, second) {
    if ([year, month, day, hour, minute, second].some((value) => !Number.isFinite(value))) {
      return null;
    }
    const parsed = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    if (
      parsed.getUTCFullYear() !== year ||
      parsed.getUTCMonth() + 1 !== month ||
      parsed.getUTCDate() !== day ||
      parsed.getUTCHours() !== hour ||
      parsed.getUTCMinutes() !== minute ||
      parsed.getUTCSeconds() !== second
    ) {
      return null;
    }
    return parsed;
  }

  _relativePathFromMediaSourceId(mediaSourceId) {
    if (!mediaSourceId || typeof mediaSourceId !== "string") {
      return "";
    }
    const prefix = "media-source://media_source/local/";
    if (!mediaSourceId.startsWith(prefix)) {
      return "";
    }
    const encodedPath = mediaSourceId.slice(prefix.length).replace(/^\/+/, "");
    if (!encodedPath) {
      return "";
    }
    const withoutQuery = encodedPath.split(/[?#]/, 1)[0];
    try {
      return decodeURIComponent(withoutQuery).replace(/^\/+/, "");
    } catch (_error) {
      return withoutQuery.replace(/^\/+/, "");
    }
  }

  _relativePathFromLocalUrl(localUrl) {
    if (!localUrl || typeof localUrl !== "string") {
      return "";
    }
    const trimmed = localUrl.trim();
    const marker = "/media/local/";
    const markerIndex = trimmed.indexOf(marker);
    if (markerIndex < 0) {
      return "";
    }
    const pathWithPrefix = trimmed.slice(markerIndex + marker.length);
    const withoutQuery = pathWithPrefix.split(/[?#]/, 1)[0];
    try {
      return decodeURIComponent(withoutQuery).replace(/^\/+/, "");
    } catch (_error) {
      return withoutQuery.replace(/^\/+/, "");
    }
  }

  _relativePathFromWorkoutImageApiUrl(url) {
    if (!url || typeof url !== "string") {
      return "";
    }
    try {
      const parsed = new URL(url, window.location.origin);
      if (parsed.pathname !== "/api/halthy/workout_image") {
        return "";
      }
      return this._normalizeArchiveKey(parsed.searchParams.get("path") || "");
    } catch (_error) {
      return "";
    }
  }

  _archiveKeyFromWorkoutItem(item, image) {
    if (!item || typeof item !== "object") {
      return this._normalizeArchiveKey(
        this._firstString(
          this._relativePathFromLocalUrl(image),
          this._relativePathFromMediaSourceId(image),
          this._relativePathFromWorkoutImageApiUrl(image)
        )
      );
    }

    return this._normalizeArchiveKey(
      this._firstString(
        item.archive_relative_path,
        item.relative_path,
        item.file_path,
        item.path,
        this._relativePathFromLocalUrl(item.archive_local_url),
        this._relativePathFromLocalUrl(item.local_url),
        this._relativePathFromMediaSourceId(item.archive_media_source_id),
        this._relativePathFromMediaSourceId(item.media_source_id),
        this._relativePathFromLocalUrl(image),
        this._relativePathFromMediaSourceId(image),
        this._relativePathFromWorkoutImageApiUrl(image)
      )
    );
  }

  _workoutIdFromItem(item) {
    if (!item || typeof item !== "object") {
      return "";
    }
    return this._firstString(
      item.workout_uuid,
      item.workout_id,
      item.uuid,
      item.workoutId
    ).trim();
  }

  _normalizeArchiveKey(pathValue) {
    if (!pathValue || typeof pathValue !== "string") {
      return "";
    }
    return pathValue.trim().replace(/^\/+/, "").replace(/\/{2,}/g, "/");
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

  _formatDistance(meters) {
    if (meters === null || meters === undefined || !Number.isFinite(meters) || meters <= 0) {
      return "";
    }
    if (meters >= 1000) {
      const km = meters / 1000;
      return `${km.toFixed(km >= 10 ? 1 : 2)} km`;
    }
    return `${Math.round(meters)} m`;
  }

  _formatDuration(seconds) {
    if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds <= 0) {
      return "";
    }
    const totalMinutes = Math.round(seconds / 60);
    if (totalMinutes < 60) {
      return `${Math.max(1, totalMinutes)} min`;
    }
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return minutes > 0 ? `${hours} h ${minutes} min` : `${hours} h`;
  }

  _formatSpeed(metersPerSecond) {
    if (
      metersPerSecond === null ||
      metersPerSecond === undefined ||
      !Number.isFinite(metersPerSecond) ||
      metersPerSecond <= 0
    ) {
      return "";
    }
    const kmh = metersPerSecond * 3.6;
    return `${kmh.toFixed(kmh >= 10 ? 1 : 2)} km/h`;
  }

  _formatRoundedUnit(value, unit) {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return "";
    }
    const rounded = Math.abs(value) >= 10 ? Math.round(value) : Number(value.toFixed(1));
    return `${rounded} ${unit}`;
  }

  _formatTemperature(value) {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return "";
    }
    return `${Math.round(value)} °C`;
  }

  _formatPercent(value) {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return "";
    }
    const normalized = value <= 1 ? value * 100 : value;
    return `${Math.round(Math.max(0, Math.min(100, normalized)))}%`;
  }

  _formatDate(value) {
    const parsed = value instanceof Date ? value : this._toDate(value);
    if (!parsed) {
      return typeof value === "string" ? value : "";
    }

    if (this._hass && typeof this._hass.formatDateTime === "function") {
      return this._hass.formatDateTime(parsed);
    }

    const locale = this._hass?.locale || {};
    const dateLanguage = typeof locale.language === "string" && locale.language.trim() ? locale.language : undefined;
    const options = {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    };

    if (locale.time_format === "12") {
      options.hour12 = true;
    } else if (locale.time_format === "24") {
      options.hour12 = false;
    }

    return new Intl.DateTimeFormat(dateLanguage, options).format(parsed);
  }

  _formatTime(value) {
    const parsed = value instanceof Date ? value : this._toDate(value);
    if (!parsed) {
      return "";
    }

    if (this._hass && typeof this._hass.formatTime === "function") {
      return this._hass.formatTime(parsed);
    }

    const locale = this._hass?.locale || {};
    const dateLanguage = typeof locale.language === "string" && locale.language.trim() ? locale.language : undefined;
    const options = {
      hour: "2-digit",
      minute: "2-digit",
    };
    if (locale.time_format === "12") {
      options.hour12 = true;
    } else if (locale.time_format === "24") {
      options.hour12 = false;
    }
    return new Intl.DateTimeFormat(dateLanguage, options).format(parsed);
  }

  _stateSignature(stateObj) {
    if (!stateObj || typeof stateObj !== "object") {
      return "missing";
    }
    const attrs = stateObj.attributes || {};
    const rawWorkouts = this._firstPresent(
      attrs[this._config?.workouts_attribute],
      attrs.saved_workouts,
      attrs.workouts,
      attrs.workout_gallery,
      attrs.gallery,
      attrs.items
    );
    return [
      String(stateObj.state ?? ""),
      this._firstString(attrs.archive_file_name),
      this._firstString(attrs.archive_relative_path),
      this._firstString(attrs.archive_local_url),
      this._firstString(attrs.archive_media_source_id),
      this._workoutDetailSignature(attrs),
      this._weatherSignature(attrs),
      this._workoutListSignature(rawWorkouts),
      this._firstString(attrs.workout_end, attrs.measurement_timestamp, attrs.last_pushed),
    ].join("|");
  }

  _workoutListSignature(rawWorkouts) {
    const list = this._coerceWorkoutList(rawWorkouts);
    if (!list.length) {
      return "0";
    }
    const first = list[0] || {};
    const last = list[list.length - 1] || {};
    const firstToken = this._firstString(
      first.workout_end,
      first.end,
      first.end_time,
      first.date,
      first.measurement_timestamp,
      first.last_pushed
    );
    const lastToken = this._firstString(
      last.workout_end,
      last.end,
      last.end_time,
      last.date,
      last.measurement_timestamp,
      last.last_pushed
    );
    return `${list.length}:${firstToken}:${this._workoutDetailSignature(first)}:${lastToken}:${this._workoutDetailSignature(last)}`;
  }

  _workoutDetailSignature(item) {
    if (!item || typeof item !== "object") {
      return "";
    }
    return [
      this._weatherSignature(item),
      String(item.workout_distance_m ?? item.distance_m ?? item.distance ?? ""),
      String(item.workout_duration_s ?? item.duration_s ?? item.duration_seconds ?? item.duration ?? ""),
      String(item.workout_active_energy_kcal ?? item.active_energy_kcal ?? item.energy_kcal ?? ""),
      String(item.avg_heart_rate_bpm ?? item.workout_avg_heart_rate_bpm ?? ""),
      String(item.lowest_heart_rate_bpm ?? item.min_heart_rate_bpm ?? ""),
      String(item.highest_heart_rate_bpm ?? item.max_heart_rate_bpm ?? ""),
      String(item.avg_speed_mps ?? item.workout_avg_speed_mps ?? item.average_speed_mps ?? ""),
      String(item.lowest_speed_mps ?? item.min_speed_mps ?? ""),
      String(item.highest_speed_mps ?? item.max_speed_mps ?? ""),
      String(item.cadence_spm ?? item.avg_cadence_spm ?? ""),
      String(item.power_w ?? item.avg_power_w ?? ""),
      String(item.respiratory_rate_brpm ?? item.avg_respiratory_rate_brpm ?? ""),
      String(item.workout_elevation_gain_m ?? item.elevation_gain_m ?? ""),
      String(item.highest_altitude_m ?? item.max_altitude_m ?? ""),
      String(item.lowest_altitude_m ?? item.min_altitude_m ?? ""),
      String(item.total_flights_climbed ?? item.workout_total_flights_climbed ?? item.flights_climbed ?? ""),
      this._zoneSignature(item.heart_rate_zones),
      this._zoneSignature(item.cycling_power_zones),
    ].join("|");
  }

  _zoneSignature(zones) {
    if (!Array.isArray(zones) || !zones.length) {
      return "";
    }
    return zones
      .map((zone) => {
        if (!zone || typeof zone !== "object") {
          return "";
        }
        return [
          String(zone.zone ?? zone.index ?? ""),
          String(zone.duration_s ?? zone.durationSeconds ?? zone.duration ?? ""),
          String(zone.min ?? ""),
          String(zone.max ?? ""),
        ].join(":");
      })
      .join(",");
  }

  _weatherSignature(item) {
    if (!item || typeof item !== "object") {
      return "";
    }
    return [
      this._firstString(item.weather_condition),
      String(item.weather_condition_raw ?? ""),
      String(item.weather_temperature_c ?? item.weather_temperature_celsius ?? ""),
      String(item.weather_humidity_percent ?? item.weather_humidity ?? ""),
    ].join(":");
  }

  _calendarIcon() {
    const value = typeof this._config?.calendar_icon === "string" ? this._config.calendar_icon.trim() : "";
    return value || "mdi:calendar-month";
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
    const nextUsers = _detectHalthyUsersFromStates(hass && hass.states);
    const nextUsersSignature = nextUsers.map((user) => `${user.id}:${user.label}`).join("|");
    if (this._usersSignature === nextUsersSignature && this.shadowRoot) {
      return;
    }
    this._users = nextUsers;
    this._usersSignature = nextUsersSignature;
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
    const calendarIconValue =
      typeof this._config.calendar_icon === "string" && this._config.calendar_icon.trim()
        ? this._config.calendar_icon.trim()
        : "mdi:calendar-month";
    const hasIconPicker = typeof customElements !== "undefined" && !!customElements.get("ha-icon-picker");
    const calendarIconField = hasIconPicker
      ? `
          <ha-icon-picker id="calendar_icon" value="${this._escapeAttr(calendarIconValue)}"></ha-icon-picker>
          <div class="hint">Start typing an icon name (for example: mdi:calendar-month).</div>
        `
      : `
          <input id="calendar_icon" type="text" placeholder="mdi:calendar-month" value="${this._escapeAttr(
            calendarIconValue
          )}" />
        `;

    const userSelectorOptions = users.map((user) => ({
      value: user.id,
      label: user.label,
    }));

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
        ha-icon-picker {
          display: block;
        }
        .hint {
          color: var(--secondary-text-color);
          font-size: 0.8rem;
        }
      </style>
      <div class="wrapper">
        <div class="field">
          <label for="user_selector">Halthy user</label>
          <ha-selector id="user_selector"></ha-selector>
          <div class="hint">
            ${
              users.length
                ? "Users are auto-detected from your Halthy integration entities."
                : "No Halthy users detected yet. Wait for first sync."
            }
          </div>
        </div>

        <div class="field">
          <label for="title_selector">Title</label>
          <ha-selector id="title_selector"></ha-selector>
        </div>

        <div class="field">
          <label for="calendar_icon">Calendar icon</label>
          ${calendarIconField}
        </div>
      </div>
    `;

    const userSelector = this.shadowRoot.getElementById("user_selector");
    const titleSelector = this.shadowRoot.getElementById("title_selector");
    const calendarIconInput = this.shadowRoot.getElementById("calendar_icon");

    if (userSelector) {
      userSelector.hass = this._hass;
      userSelector.selector = {
        select: {
          mode: "dropdown",
          options: userSelectorOptions,
          custom_value: false,
          multiple: false,
        },
      };
      if ("value" in userSelector) {
        userSelector.value = userSelectorOptions.some((option) => option.value === selectedUser) ? selectedUser : "";
      }

      const onUserChanged = (event) => {
        const nextUser = _sanitizeIdentifier(event?.detail?.value ?? event?.target?.value);
        if (nextUser) {
          this._emitConfig({
            user: nextUser,
            entity: _entityFromUser(nextUser),
          });
        }
      };

      userSelector.addEventListener("value-changed", onUserChanged);
      userSelector.addEventListener("change", onUserChanged);
    }

    if (titleSelector) {
      titleSelector.hass = this._hass;
      titleSelector.selector = { text: {} };
      if ("value" in titleSelector) {
        titleSelector.value = String(this._config.title || "");
      }

      const onTitleChanged = (event) => {
        this._emitConfig({
          title: String(event?.detail?.value ?? event?.target?.value ?? ""),
        });
      };

      titleSelector.addEventListener("value-changed", onTitleChanged);
      titleSelector.addEventListener("change", onTitleChanged);
    }

    if (calendarIconInput) {
      if ("value" in calendarIconInput && !calendarIconInput.value) {
        calendarIconInput.value = calendarIconValue;
      }

      const onCalendarIconChanged = (event) => {
        const value = String(event?.detail?.value ?? event?.target?.value ?? "").trim();
        this._emitConfig({
          calendar_icon: value || "mdi:calendar-month",
        });
      };

      calendarIconInput.addEventListener("value-changed", onCalendarIconChanged);
      calendarIconInput.addEventListener("change", onCalendarIconChanged);
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
