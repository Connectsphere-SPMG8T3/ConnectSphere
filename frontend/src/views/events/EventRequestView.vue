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
import { EVENT_TIMEZONES } from "@/features/events/timezones";
import { FACILITIES, LAYOUTS, emptyEvent, useEventsStore } from "@/stores/events";

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
    if (!form.expectedAttendance || Number(form.expectedAttendance) < 1) {
      errors.expectedAttendance = "Enter expected attendance of at least 1.";
    }
    if (!form.layoutPreference) errors.layoutPreference = "Choose a layout.";
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

async function save() {
  if (!validateSubmission()) return;
  try {
    const event = isNew.value && intent.value === "submit"
      ? await eventsStore.createAndSubmit(form)
      : isNew.value
        ? await eventsStore.saveDraft(form)
        : intent.value === "submit"
          ? await eventsStore.submit(form.id, form)
          : await eventsStore.updateDraft(form.id, form);
    if (intent.value === "submit") {
      pristineSnapshot.value = serializeForm(form);
      showToast("Request submitted");
      await router.push({ name: "dashboard-organiser" });
    } else {
      showToast(isReturned.value ? "Changes saved" : "Draft saved");
      Object.assign(form, event);
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
  try {
    if (!eventsStore.events.length) await eventsStore.load();
  } catch {
    return;
  }
  const stored = eventsStore.events.find(
    (event) => event.id === route.query.id && ["draft", "returned"].includes(event.status),
  );
  if (stored?.status === "returned") {
    // The list omits the amendment; the single-event read carries it.
    try {
      Object.assign(form, await eventsStore.get(stored.id));
    } catch {
      return;
    }
  } else if (stored) {
    Object.assign(form, stored);
  }
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
            <textarea id="event-description" v-model="form.description" rows="4" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" :class="flagFor('description') ? 'bg-bauhaus-yellow/30' : ''" :aria-describedby="flagFor('description') ? 'event-description-flag' : undefined" :data-flagged="flagFor('description') ? 'true' : undefined" placeholder="Add useful context for the planning team."></textarea>
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
            <div>
              <BauhausSelect v-model="form.layoutPreference" label="Preferred layout" required :options="LAYOUTS" placeholder="Choose a layout" :flag="flagFor('layoutPreference')" />
              <p v-if="fieldErrors.layoutPreference" class="mt-2 text-xs font-bold uppercase tracking-wide text-bauhaus-red">{{ fieldErrors.layoutPreference }}</p>
            </div>
          </div>
          <div class="sm:col-span-2">
            <BauhausCheckboxGroup v-model="form.facilitiesRequired" label="Facilities required" :options="FACILITIES" :flag="flagFor('facilitiesRequired')" />
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
