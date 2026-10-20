<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { onBeforeRouteLeave, useRoute } from "vue-router";
import { useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import AmendmentBanner from "@/components/events/AmendmentBanner.vue";
import ResubmitEventModal from "@/components/events/ResubmitEventModal.vue";
import { showToast } from "@/composables/useToast";
import { FLAG_TEXT, flaggedFormKeys } from "@/features/events/amendment";
import { getEarliestEventDate, getRegistrationClosingError, getRegistrationOpeningError, getSingaporeDateString, isEventDateAfterToday } from "@/features/events/dateValidation";
import { EVENT_TIMEZONES, toZonedIso } from "@/features/events/timezones";
import { FACILITIES, LAYOUTS, emptyEvent, emptySpace, spaceToPayload, useEventsStore } from "@/stores/events";

const SPACE_PURPOSES = [
  { value: "main_venue", label: "Main venue" },
  { value: "breakout_room", label: "Breakout room" },
  { value: "workshop_room", label: "Workshop room" },
  { value: "registration", label: "Registration/check-in" },
  { value: "catering", label: "Catering area" },
  { value: "networking", label: "Networking area" },
  { value: "other", label: "Other" },
];
const OTHER_SPACE_PURPOSE = "other";

const router = useRouter();
const route = useRoute();
const eventsStore = useEventsStore();
const form = reactive(emptyEvent());
const fieldErrors = ref({});
const intent = ref("draft");
const isNew = computed(() => !form.id);
// SCRUM-33: a returned request is amended here and resubmitted to its coordinator.
const isReturned = computed(() => form.status === "returned");
const flaggedKeys = computed(() => flaggedFormKeys(form.amendment?.flagged_fields));
const isResubmitModalOpen = ref(false);
const isSavingSpace = ref(false);

function flagFor(key) {
  return flaggedKeys.value.has(key) ? FLAG_TEXT : "";
}

const earliestEventDate = computed(() => getEarliestEventDate(form.eventTimezone));
const earliestRegistrationDateTime = computed(() => `${earliestEventDate.value}T00:00`);
const isLeaveModalOpen = ref(false);
const isSubmitModalOpen = ref(false);
const pendingRoute = ref(null);
const allowNavigation = ref(false);
const pristineSnapshot = ref(serializeForm(form));
const isDirty = computed(() => serializeForm(form) !== pristineSnapshot.value);

function serializeForm(event) {
  return JSON.stringify(event);
}

function requestLeave(target) {
  if (!isDirty.value) {
    router.push(target);
    return;
  }
  pendingRoute.value = target;
  isLeaveModalOpen.value = true;
}

async function confirmLeave() {
  const target = pendingRoute.value;
  isLeaveModalOpen.value = false;
  pendingRoute.value = null;
  allowNavigation.value = true;
  if (target) await router.push(target);
}

function stayOnPage() {
  isLeaveModalOpen.value = false;
  pendingRoute.value = null;
}

function requestSubmit() {
  intent.value = "submit";
  if (!validateSubmission()) return;
  if (isReturned.value) isResubmitModalOpen.value = true;
  else isSubmitModalOpen.value = true;
}

function confirmSubmit() {
  isSubmitModalOpen.value = false;
  save();
}

async function confirmResubmit(note) {
  try {
    await persistSpaces(form.id, form.spaces);
    await eventsStore.resubmit(form.id, form, note);
  } catch {
    return; // The modal stays open and shows the API's message.
  }
  isResubmitModalOpen.value = false;
  pristineSnapshot.value = serializeForm(form);
  showToast("Request resubmitted");
  await router.push({ name: "dashboard-organiser" });
}

function handleBeforeUnload(event) {
  if (!isDirty.value) return;
  event.preventDefault();
  event.returnValue = "";
}

function validateSubmission() {
  const errors = {};
  if (!form.name.trim()) errors.name = "Enter an event title.";
  else if (form.name.trim().length < 3) errors.name = "Use at least 3 characters.";
  if (intent.value === "submit") {
    if (!form.purpose.trim()) errors.purpose = "Enter the event purpose.";
    if (!form.date) errors.date = "Enter the event date.";
    else if (!isEventDateAfterToday(form.date, getSingaporeDateString(new Date(), form.eventTimezone))) {
      errors.date = "Event date must be after today.";
    }
    if (!form.startTime) errors.startTime = "Enter the start time.";
    if (!form.endTime) errors.endTime = "Enter the end time.";
    if (form.startTime && form.endTime && form.endTime <= form.startTime) {
      errors.endTime = "End time must be after the start time.";
    }
    const spaceErrors = form.spaces.map((space) => validateSpace(space, form));
    if (spaceErrors.some((spaceError) => Object.keys(spaceError).length)) errors.spaces = spaceErrors;
    if (form.registrationEnabled && !form.registrationCapacity) {
      errors.registrationCapacity = "Enter a registration capacity.";
    }
    if (form.registrationEnabled && !form.registrationOpensAt) {
      errors.registrationOpensAt = "Enter when registration should open.";
    }
    if (form.registrationEnabled && !form.registrationClosesAt) {
      errors.registrationClosesAt = "Enter when registration should close.";
    }
    if (form.registrationEnabled && getRegistrationOpeningError(form.registrationOpensAt, getSingaporeDateString(new Date(), form.eventTimezone))) {
      errors.registrationOpensAt = getRegistrationOpeningError(form.registrationOpensAt, getSingaporeDateString(new Date(), form.eventTimezone));
    }
    const registrationClosingError = getRegistrationClosingError({
      opensAt: form.registrationOpensAt,
      closesAt: form.registrationClosesAt,
      eventDate: form.date,
      eventEndTime: form.endTime,
    }, getSingaporeDateString(new Date(), form.eventTimezone));
    if (form.registrationEnabled && registrationClosingError) errors.registrationClosesAt = registrationClosingError;
  }
  fieldErrors.value = errors;
  return Object.keys(errors).length === 0;
}

function validateSpace(space, event = form) {
  const errors = {};
  if (!space.purposeSelection) errors.label = "Choose a space purpose.";
  else if (space.purposeSelection === OTHER_SPACE_PURPOSE && !space.customPurpose.trim()) {
    errors.label = "Enter a custom purpose.";
  }
  if (!space.expectedPax || Number(space.expectedPax) < 1) errors.expectedPax = "Enter expected pax of at least 1.";
  if (!space.layoutPreference) errors.layoutPreference = "Choose a layout.";
  if (!space.useEventSchedule) {
    if (!space.startTime) errors.startTime = "Enter a start time for this space.";
    if (!space.endTime) errors.endTime = "Enter an end time for this space.";
    if (space.startTime && space.endTime) {
      if (space.endTime <= space.startTime) {
        errors.endTime = "Space end time must be after its start time.";
      }
      if (!event.date || !event.startTime || !event.endTime) {
        errors.startTime = "Set the overall event schedule before this space schedule.";
      } else {
        if (space.startTime < event.startTime) {
          errors.startTime = "Space times must be within the event's overall schedule.";
        }
        if (space.endTime > event.endTime) {
          errors.endTime = "Space times must be within the event's overall schedule.";
        }
      }
    }
  }
  return errors;
}

function addSpace() {
  form.spaces.push(newSpace());
}

function copySpace(space) {
  form.spaces.push(Object.assign(newSpace(), {
    label: space.label,
    expectedPax: space.expectedPax,
    layoutPreference: space.layoutPreference,
    facilitiesRequired: [...(space.facilitiesRequired ?? [])],
    useEventSchedule: space.useEventSchedule,
    purposeSelection: space.purposeSelection,
    customPurpose: space.customPurpose,
    startTime: space.startTime,
    endTime: space.endTime,
  }));
}

function newSpace() {
  return { ...emptySpace(), purposeSelection: "", customPurpose: "", startTime: "", endTime: "" };
}

function spaceWithPurpose(space) {
  const purpose = SPACE_PURPOSES.find(
    (option) => option.value !== OTHER_SPACE_PURPOSE && option.label === space.label,
  );
  return {
    ...space,
    purposeSelection: purpose?.value ?? OTHER_SPACE_PURPOSE,
    customPurpose: purpose ? "" : space.label ?? "",
    startTime: space.startsAt?.split("T")[1] ?? "",
    endTime: space.endsAt?.split("T")[1] ?? "",
  };
}

function setSpacePurpose(space, value) {
  space.purposeSelection = value;
  if (value === OTHER_SPACE_PURPOSE) {
    space.label = space.customPurpose;
    return;
  }
  space.label = SPACE_PURPOSES.find((option) => option.value === value)?.label ?? "";
}

function setCustomPurpose(space, value) {
  space.customPurpose = value;
  space.label = value;
}

function setFormEvent(event) {
  Object.assign(form, event);
  form.spaces = (event.spaces ?? []).map(spaceWithPurpose);
}

async function removeSpace(space) {
  if (!space.id) {
    const index = form.spaces.indexOf(space);
    if (index !== -1) form.spaces.splice(index, 1);
    return;
  }
  if (!window.confirm(`Remove ${space.label}?`)) return;
  isSavingSpace.value = true;
  try {
    await eventsStore.removeSpace(form.id, space.id);
    const refreshed = await eventsStore.get(form.id);
    setFormEvent(refreshed);
  } catch {
    // The store exposes the API message in the form alert.
  } finally {
    isSavingSpace.value = false;
  }
}

async function persistSpaces(eventId, spaces) {
  for (const space of spaces) {
    if (Object.keys(validateSpace(space, form)).length) continue;
    const spaceWithEventDate = {
      ...space,
      startsAt: space.startTime ? `${form.date}T${space.startTime}` : "",
      endsAt: space.endTime ? `${form.date}T${space.endTime}` : "",
    };
    const payload = spaceToPayload(spaceWithEventDate, form.eventTimezone);
    if (space.id) await eventsStore.updateSpace(eventId, space.id, { ...payload, version: space.version });
    else await eventsStore.createSpace(eventId, payload);
  }
}

async function save() {
  if (!validateSubmission()) return;
  try {
    let event;
    if (isNew.value) {
      const pendingSpaces = [...form.spaces];
      event = await eventsStore.saveDraft(form);
      Object.assign(form, event);
      form.spaces = pendingSpaces;
      await persistSpaces(event.id, pendingSpaces);
      event = await eventsStore.get(event.id);
      if (intent.value !== "submit") event.spaces.push(...pendingSpaces.filter((space) => Object.keys(validateSpace(space, form)).length));
      if (intent.value === "submit") event = await eventsStore.submit(event.id, event);
    } else {
      const pendingSpaces = [...form.spaces];
      event = await eventsStore.updateDraft(form.id, form);
      await persistSpaces(event.id, pendingSpaces);
      event = await eventsStore.get(event.id);
      if (intent.value !== "submit") event.spaces.push(...pendingSpaces.filter((space) => Object.keys(validateSpace(space, form)).length));
      if (intent.value === "submit") event = await eventsStore.submit(event.id, event);
    }
    if (intent.value === "submit") {
      pristineSnapshot.value = serializeForm(form);
      showToast("Request submitted");
      await router.push({ name: "dashboard-organiser" });
    } else {
      showToast(isReturned.value ? "Changes saved" : "Draft saved");
      setFormEvent(event);
      pristineSnapshot.value = serializeForm(form);
      fieldErrors.value = {};
    }
  } catch {
    // The store exposes the API message in the form alert.
  }
}

function chooseIntent(nextIntent) {
  if (nextIntent === "submit") {
    requestSubmit();
    return;
  }
  intent.value = nextIntent;
  save();
}

onBeforeRouteLeave((to) => {
  if (!isDirty.value || allowNavigation.value) return true;
  pendingRoute.value = to;
  isLeaveModalOpen.value = true;
  return false;
});

onMounted(async () => {
  if (route.query.id) {
    // Always read the event itself: a cached list can hold a stale status (and
    // omits the amendment), and trusting it left a blank form whose Save draft
    // would create a duplicate event.
    let event;
    try {
      event = await eventsStore.get(route.query.id);
    } catch {
      return; // eventsStore.error is shown in the page alert.
    }
    if (!["draft", "returned"].includes(event.status)) {
      allowNavigation.value = true;
      await router.replace({ name: "event-detail", params: { id: event.id } });
      return;
    }
    setFormEvent(event);
  }
  if (!form.spaces.length) form.spaces.push(newSpace());
  pristineSnapshot.value = serializeForm(form);
});

onMounted(() => window.addEventListener("beforeunload", handleBeforeUnload));
onBeforeUnmount(() => window.removeEventListener("beforeunload", handleBeforeUnload));
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <BauhausCard background="yellow" accent="square" accent-color="bauhaus-red" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event request</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        {{ isNew ? "Start an event" : isReturned ? "Amend your request" : "Edit your draft" }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Save the request as a draft while details are taking shape, or submit it once the required planning information is ready.
      </p>
    </BauhausCard>

    <AmendmentBanner v-if="isReturned && form.amendment" :amendment="form.amendment" class="mb-10" />

    <p
      v-if="eventsStore.error && !isResubmitModalOpen"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
    >
      {{ eventsStore.error }}
    </p>

    <form novalidate class="grid gap-8 lg:grid-cols-[1.35fr_0.65fr]" @submit.prevent="chooseIntent('submit')">
      <BauhausCard background="white" accent="none">
        <div class="grid gap-6 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <BauhausInput v-model="form.name" label="Event title" required :error="fieldErrors.name" :flag="flagFor('name')" placeholder="Regional planning workshop" />
          </div>
          <div class="sm:col-span-2">
            <BauhausInput v-model="form.purpose" label="Purpose" required :error="fieldErrors.purpose" :flag="flagFor('purpose')" placeholder="What is this event for?" />
          </div>
          <div class="sm:col-span-2 flex flex-col gap-2">
            <label for="event-description" class="text-xs font-bold uppercase tracking-widest">Description</label>
            <textarea id="event-description" v-model="form.description" rows="4" class="border-2 border-ink px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" :class="flagFor('description') ? 'bg-bauhaus-yellow/30' : 'bg-canvas'" :aria-describedby="flagFor('description') ? 'event-description-flag' : undefined" :data-flagged="flagFor('description') ? 'true' : undefined" placeholder="Add useful context for the planning team."></textarea>
            <p v-if="flagFor('description')" id="event-description-flag" class="border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide text-ink">{{ FLAG_TEXT }}</p>
          </div>
          <BauhausInput v-model="form.date" label="Proposed event date" type="date" required :min="earliestEventDate" :error="fieldErrors.date" :flag="flagFor('date')" />
          <BauhausSelect v-model="form.eventTimezone" label="Event timezone" required :options="EVENT_TIMEZONES" :flag="flagFor('eventTimezone')" />
          <div class="sm:col-span-2 grid gap-6 sm:grid-cols-2">
            <BauhausInput v-model="form.startTime" label="Proposed start time" type="time" required :error="fieldErrors.startTime" :flag="flagFor('startTime')" />
            <BauhausInput v-model="form.endTime" label="Proposed end time" type="time" required :error="fieldErrors.endTime" :flag="flagFor('endTime')" />
          </div>
          <div class="sm:col-span-2 grid gap-6 sm:grid-cols-2">
            <BauhausInput v-model="form.expectedAttendance" label="Expected attendance" type="number" required :error="fieldErrors.expectedAttendance" :flag="flagFor('expectedAttendance')" />
          </div>
          <div class="sm:col-span-2 border-4 border-ink bg-bauhaus-yellow/20 p-4 shadow-hard sm:p-6">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Venue requirements</p>
                <h2 class="mt-1 text-2xl font-black uppercase tracking-tight">Plan each space</h2>
                <p class="mt-2 text-sm font-bold">Suggest venue layouts for your event.</p>
              </div>
              <span class="border-2 border-ink bg-canvas px-2 py-1 text-xs font-black uppercase tracking-widest">{{ form.spaces.length }} spaces</span>
            </div>

            <div class="mt-6 grid gap-4">
              <div v-for="(space, index) in form.spaces" :key="space.id || `draft-space-${index}`" class="border-2 border-dashed border-ink bg-bauhaus-yellow/20 p-4">
                <div class="grid gap-4 sm:grid-cols-2">
                  <BauhausSelect
                    :model-value="space.purposeSelection"
                    label="Purpose"
                    aria-label="Space purpose"
                    required
                    :options="SPACE_PURPOSES"
                    placeholder="Choose a purpose"
                    :error="!space.purposeSelection ? fieldErrors.spaces?.[index]?.label : ''"
                    @update:model-value="setSpacePurpose(space, $event)"
                  />
                  <BauhausInput
                    v-if="space.purposeSelection === OTHER_SPACE_PURPOSE"
                    :model-value="space.customPurpose"
                    label="Custom purpose"
                    required
                    placeholder="Describe this space"
                    :error="fieldErrors.spaces?.[index]?.label"
                    @update:model-value="setCustomPurpose(space, $event)"
                  />
                  <BauhausInput v-model="space.expectedPax" label="Expected pax" type="number" required :error="fieldErrors.spaces?.[index]?.expectedPax" />
                  <BauhausSelect v-model="space.layoutPreference" label="Preferred layout" required :options="LAYOUTS" placeholder="Choose a layout" :error="fieldErrors.spaces?.[index]?.layoutPreference" />
                  <div class="sm:col-span-2"><BauhausCheckboxGroup v-model="space.facilitiesRequired" label="Venue facilities required" :options="FACILITIES" /></div>
                  <div class="sm:col-span-2">
                    <label class="inline-flex items-center gap-2 border-2 border-ink bg-canvas px-3 py-2 text-xs font-bold uppercase tracking-wide shadow-hard">
                      <input v-model="space.useEventSchedule" data-testid="space-schedule-toggle" type="checkbox" class="h-4 w-4 accent-bauhaus-red" />
                      Use full event duration
                    </label>
                    <p v-if="space.useEventSchedule" class="mt-2 text-sm font-medium">
                      Uses {{ form.date || "the event date" }} · {{ form.startTime || "start" }}–{{ form.endTime || "end" }} ({{ form.eventTimezone }})
                    </p>
                    <div v-else class="mt-4 grid gap-4 sm:grid-cols-2">
                      <BauhausInput
                        v-model="space.startTime"
                        label="Start time"
                        type="time"
                        :min="form.startTime || undefined"
                        :max="form.endTime || undefined"
                        :error="fieldErrors.spaces?.[index]?.startTime"
                      />
                      <BauhausInput
                        v-model="space.endTime"
                        label="End time"
                        type="time"
                        :min="form.startTime || undefined"
                        :max="form.endTime || undefined"
                        :error="fieldErrors.spaces?.[index]?.endTime"
                      />
                    </div>
                  </div>
                </div>
                <div class="mt-4 flex flex-wrap gap-3">
                  <BauhausButton type="button" variant="yellow" :disabled="isSavingSpace" @click="copySpace(space)">Copy space</BauhausButton>
                  <BauhausButton v-if="form.spaces.length > 1" type="button" variant="yellow" :disabled="isSavingSpace" @click="removeSpace(space)">Remove space</BauhausButton>
                </div>
              </div>
            </div>

            <BauhausButton type="button" class="mt-4" variant="yellow" :disabled="isSavingSpace" @click="addSpace">Add space request</BauhausButton>
          </div>
          <div class="sm:col-span-2">
            <BauhausInput v-model="form.accessibilityNeeds" label="Accessibility needs" :flag="flagFor('accessibilityNeeds')" placeholder="Step-free access, hearing loop, etc." />
          </div>
          <div class="sm:col-span-2">
            <BauhausInput v-model="form.preliminaryEquipmentNeeds" label="Preliminary equipment needs" :flag="flagFor('preliminaryEquipmentNeeds')" placeholder="Wireless microphones, projector, etc." />
          </div>
        </div>
      </BauhausCard>

      <aside class="flex flex-col gap-6">
        <BauhausCard background="blue" accent="circle" accent-color="bauhaus-yellow">
          <h2 class="text-2xl font-black uppercase tracking-tight">Registration</h2>
          <label class="mt-5 flex items-center gap-3 text-sm font-bold uppercase tracking-wide">
            <input v-model="form.registrationEnabled" type="checkbox" class="h-5 w-5 accent-bauhaus-yellow" />
            Enable attendee registration
          </label>
          <p v-if="flagFor('registrationEnabled')" class="mt-2 border-l-4 border-bauhaus-yellow pl-2 text-xs font-bold uppercase tracking-wide">{{ FLAG_TEXT }}</p>
          <div v-if="form.registrationEnabled" class="mt-5 flex flex-col gap-5">
            <BauhausInput v-model="form.registrationCapacity" label="Registration capacity" required type="number" :error="fieldErrors.registrationCapacity" :flag="flagFor('registrationCapacity')" />
            <BauhausInput v-model="form.registrationOpensAt" label="Registration opens" required type="datetime-local" :min="earliestRegistrationDateTime" :error="fieldErrors.registrationOpensAt" :flag="flagFor('registrationOpensAt')" />
            <BauhausInput v-model="form.registrationClosesAt" label="Registration closes" required type="datetime-local" :min="earliestRegistrationDateTime" :error="fieldErrors.registrationClosesAt" :flag="flagFor('registrationClosesAt')" />
          </div>
        </BauhausCard>

        <BauhausCard background="white" accent="none">
          <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Workflow</p>
          <p class="mt-2 text-sm font-medium">Drafts stay private to you. Submission sends a complete request for coordinator review.</p>
          <div class="mt-6 flex flex-col gap-3">
            <BauhausButton type="button" variant="yellow" :disabled="eventsStore.isSaving" @click="chooseIntent('draft')">
              {{ eventsStore.isSaving ? "Saving..." : isReturned ? "Save changes" : "Save draft" }}
            </BauhausButton>
            <BauhausButton type="submit" variant="primary" :disabled="eventsStore.isSaving">{{ isReturned ? "Resubmit" : "Submit request" }}</BauhausButton>
            <BauhausButton type="button" variant="outline" :disabled="eventsStore.isSaving" @click="requestLeave({ name: 'dashboard-organiser' })">Cancel</BauhausButton>
          </div>
        </BauhausCard>
      </aside>
    </form>
    <ConfirmModal :open="isLeaveModalOpen" @confirm="confirmLeave" @stay="stayOnPage" />
    <ConfirmModal
      :open="isSubmitModalOpen"
      title="Submit event request?"
      message="After submission, the request will be sent for coordinator review. You will not be able to edit it directly unless it is returned for amendment."
      confirm-label="Confirm and submit"
      cancel-label="Review request"
      @confirm="confirmSubmit"
      @stay="isSubmitModalOpen = false"
    />
    <ResubmitEventModal
      :open="isResubmitModalOpen"
      :event-name="form.name"
      :busy="eventsStore.isSaving"
      :error="isResubmitModalOpen ? eventsStore.error : null"
      @confirm="confirmResubmit"
      @cancel="isResubmitModalOpen = false"
    />
  </main>
</template>
