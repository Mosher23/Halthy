// Exercise real card metadata rendering without a browser or health data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const definitions = new Map();
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../custom_components/halthy/halthy-workout-card.js'), 'utf8'), {
  HTMLElement: class {},
  customElements: { get: name => definitions.get(name), define: (name, value) => definitions.set(name, value) },
  window: { customCards: [] }, console, Intl, Date, URL, Set, Map,
});
const card = Object.create(definitions.get('halthy-workout-card').prototype);
card._config = {};
const attributes = {
  workout_duration_s: 162, workout_machine_duration_s: 161, workout_distance_m: 822,
  workout_device_name: 'Matrix Indoor Bike', workout_device_model: 'Bike',
  workout_step_count: 197, total_flights_climbed: 12, cadence_spm: 60, workout_cadence_unit: 'rpm', power_w: 100,
};
const html = card._renderWorkoutDetails({ details: card._workoutDetailsFromItem(attributes) });
for (const text of ['Matrix Indoor Bike', 'Machine duration', '197', '12', '60 rpm', '100 W']) {
  assert.ok(html.includes(text), `Missing GymKit detail: ${text}`);
}
assert.notEqual(card._workoutDetailSignature(attributes), card._workoutDetailSignature({ ...attributes, workout_device_name: 'Updated Bike' }));
const unsafe = card._renderWorkoutDetails({ details: card._workoutDetailsFromItem({ ...attributes, workout_device_name: '<img src=x onerror=bad()>' }) });
assert.ok(!unsafe.includes('<img src=x'));
assert.ok(unsafe.includes('&lt;img'));
console.log('GymKit card rendering and escaping checks passed.');
