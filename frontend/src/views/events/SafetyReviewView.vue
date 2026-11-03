<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import SafetyChecklist from "@/components/events/SafetyChecklist.vue";
import SafetyDecisionDetails from "@/components/events/SafetyDecisionDetails.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import { showToast } from "@/composables/useToast";
import { exitConfirmationText } from "@/features/equipment/technical";
import { buildChecklist, canApprove, hasConcern, missingMarks } from "@/features/events/safetyChecklist";
import { displaySafetyTime } from "@/features/events/safetyDecision";
import { useSafetyDecisionStore } from "@/features/events/safetyDecisionStore";

const route = useRoute();
const router = useRouter();
const safety = useSafetyDecisionStore();
// CR-108: the comment the organiser sees and the officer's private notes are separate texts.
const organiserComment = ref("");
const privateNote = ref("");
const marks = ref({});
const bookingIds = ref([]);
const rejectedBookingId = ref(null);
const equipmentIds = ref([]);
const pendingKind = ref(null);
const review = computed(() => safety.review);
const venueBookingIds = computed(() => (review.value?.venues ?? []).map((venue) => venue.booking_id));
const missing = computed(() => missingMarks(marks.value, venueBookingIds.value));
const complete = computed(() => missing.value.length === 0);
const approvable = computed(() => canApprove(marks.value, venueBookingIds.value));
const concern = computed(() => hasConcern(marks.value, venueBookingIds.value));
const hasComment = computed(() => organiserComment.value.trim() !== "");
const missingText = computed(() => `${missing.value.length} checklist ${missing.value.length === 1 ? "mark" : "marks"} still to make.`);
function resetForm() {
  organiserComment.value = "";
  privateNote.value = "";
  marks.value = {};
  bookingIds.value = [];
  equipmentIds.value = [];
  rejectedBookingId.value = null;
}
const confirmations = {
  approve: { title: "Approve this event?", label: "Approve", message: "The event will be Confirmed. The organiser and staff will be notified.", toast: "Event approved" },
  requestChanges: { title: "Request changes?", label: "Request changes", message: "The event returns to Planning. No booking or equipment changes status; the coordinator decides what to change.", toast: "Changes requested" },
  reject: { title: "Reject this venue for the event?", label: "Reject", message: "The event returns to Planning and this venue's booking is flagged Safety rejected. It is not released, and the event itself is not rejected.", toast: "Venue rejected" },
};
const confirmation = computed(() => confirmations[pendingKind.value]);

async function confirmDecision() {
  if (safety.loading || !pendingKind.value) return;
  if (review.value?.event.id !== route.params.id) {
    pendingKind.value = null;
    safety.error = "This review is out of date. Reload the event before deciding.";
    return;
  }
  const kind = pendingKind.value;
  pendingKind.value = null;
  const text = organiserComment.value.trim();
  const common = {
    checklist: buildChecklist(marks.value, venueBookingIds.value),
    organiser_comment: text || null,
    private_note: privateNote.value.trim() || null,
  };
  const payload = kind === "approve" ? common : kind === "reject" ? { ...common, booking_id: rejectedBookingId.value } : {
    ...common, booking_ids: [...bookingIds.value], equipment_request_ids: [...equipmentIds.value],
  };
  try {
    await safety.decide(kind, route.params.id, payload);
    resetForm();
    showToast(confirmations[kind].toast);
    await router.push({ name: "dashboard-safety" });
  } catch {
    // The API's refusal is shown in the page alert.
  }
}
watch(() => route.params.id, (id) => {
  resetForm();
  pendingKind.value = null;
  if (id) safety.loadReview(id);
}, { immediate: true });
</script>

<template>
  <main class="break-words py-8">
    <BauhausButton variant="outline" class="mb-8" @click="router.push({ name: 'dashboard-safety' })">Back to queue</BauhausButton>
    <p v-if="safety.error" role="alert" class="mb-6 border-4 border-ink p-4 font-bold">{{ safety.error }}</p>
    <p v-if="safety.loading && !review" class="font-bold">Loading safety review…</p>
    <template v-if="review">
      <BauhausCard background="yellow" accent="none" class="mb-8">
        <h1 class="text-4xl font-bold leading-tight sm:text-5xl">{{ review.event.name }}</h1>
        <dl class="mt-6 grid gap-4 sm:grid-cols-2">
          <div><dt class="font-bold">Organiser</dt><dd>{{ review.event.organiser_name }}</dd></div>
          <div><dt class="font-bold">Coordinator</dt><dd>{{ review.event.coordinator_name ?? 'Not provided' }}</dd></div>
          <div><dt class="font-bold">Starts</dt><dd>{{ displaySafetyTime(review.event.starts_at) }}</dd></div>
          <div><dt class="font-bold">Ends</dt><dd>{{ displaySafetyTime(review.event.ends_at) }}</dd></div>
          <div><dt class="font-bold">Expected attendance</dt><dd>{{ review.event.expected_attendance ?? 'Not provided' }}</dd></div>
          <div><dt class="font-bold">Accessibility needs</dt><dd>{{ review.event.accessibility_needs || 'None specified' }}</dd></div>
        </dl>
      </BauhausCard>
      <div class="grid min-w-0 gap-8 lg:grid-cols-2">
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-bold">Venues</h2>
          <div v-for="venue in review.venues" :key="venue.booking_id" class="mt-6 border-t-2 border-ink pt-4">
            <h3 class="text-xl font-bold">{{ venue.venue_name }}</h3>
            <dl class="mt-3 grid gap-3">
              <div><dt class="font-bold">Booking status</dt><dd>{{ venue.booking_status }}</dd></div>
              <div><dt class="font-bold">Capacity</dt><dd>{{ venue.capacity }}</dd></div>
              <div><dt class="font-bold">Layouts</dt><dd>{{ venue.layouts.join(', ') || 'Not provided' }}</dd></div>
              <div><dt class="font-bold">Accessibility features</dt><dd>{{ venue.accessibility_features.join(', ') || 'None specified' }}</dd></div>
              <div><dt class="font-bold">Attendance against capacity</dt><dd>{{ review.event.expected_attendance ?? 'Not provided' }} / {{ venue.capacity }} ({{ venue.attendance_to_capacity == null ? 'Not provided' : `${Math.round(venue.attendance_to_capacity * 100)}%` }})</dd></div>
              <div><dt class="font-bold">Emergency access</dt><dd class="whitespace-pre-wrap [overflow-wrap:anywhere]">{{ venue.emergency_access ?? 'Not recorded' }}</dd></div>
              <div><dt class="font-bold">Restrictions</dt><dd class="whitespace-pre-wrap [overflow-wrap:anywhere]">{{ venue.restrictions ?? 'Not recorded' }}</dd></div>
            </dl>
          </div>
        </BauhausCard>
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-bold">Equipment</h2>
          <p v-if="!review.equipment_lines.length" class="mt-4">No equipment requested</p>
          <ul v-else class="mt-4 space-y-3"><li v-for="line in review.equipment_lines" :key="line.id">{{ line.equipment_name }} × {{ line.quantity }} — {{ line.status }}</li></ul>
          <p class="mt-6 font-bold">Exit confirmation</p><p v-if="review.exit_confirmation">Equipment does not block exits or walkways.</p><p>{{ exitConfirmationText(review.exit_confirmation) }}</p>
        </BauhausCard>
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-bold">Registration — for information</h2>
          <p class="mt-4">{{ review.event.registration.enabled ? 'Enabled' : 'Not enabled' }}</p>
          <dl v-if="review.event.registration.enabled" class="mt-3 grid gap-3">
            <div><dt class="font-bold">Capacity</dt><dd>{{ review.event.registration.capacity ?? 'Not provided' }}</dd></div>
            <div><dt class="font-bold">Opens</dt><dd>{{ displaySafetyTime(review.event.registration.opens_at) }}</dd></div>
            <div><dt class="font-bold">Closes</dt><dd>{{ displaySafetyTime(review.event.registration.closes_at) }}</dd></div>
          </dl>
        </BauhausCard>
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-bold">Earlier safety decisions</h2>
          <p v-if="!safety.decisions.length" class="mt-4">No earlier safety decisions</p>
          <ul v-else class="mt-4 space-y-4">
            <li v-for="decision in safety.decisions" :key="decision.id">
              <SafetyDecisionDetails :decision="decision" />
            </li>
          </ul>
        </BauhausCard>
        <BauhausCard background="white" accent="none" class="lg:col-span-2">
          <h2 class="text-2xl font-bold">Safety decision</h2>
          <p class="mt-2 text-sm">Mark every factor for each venue and for the whole event before you decide.</p>
          <div class="mt-6">
            <SafetyChecklist v-model="marks" :venues="review.venues" :disabled="safety.loading" />
          </div>
          <label for="safety-organiser-comment" class="mt-6 block font-bold">Comment for the organiser</label>
          <textarea id="safety-organiser-comment" v-model="organiserComment" maxlength="1000" rows="4" aria-describedby="safety-organiser-comment-hint" class="mt-2 w-full border-2 border-ink bg-canvas p-3" :disabled="safety.loading" />
          <p id="safety-organiser-comment-hint" class="mt-2 text-sm">Required to request changes or reject. The organiser sees this with the outcome, so say what needs to change.</p>
          <label for="safety-private-note" class="mt-6 block font-bold">Private notes (optional)</label>
          <textarea id="safety-private-note" v-model="privateNote" maxlength="1000" rows="3" aria-describedby="safety-private-note-hint" class="mt-2 w-full border-2 border-ink bg-canvas p-3" :disabled="safety.loading" />
          <p id="safety-private-note-hint" class="mt-2 text-sm">Only the assigned coordinator and Safety Officers see these; the organiser never does. Note any crowd-movement concerns here.</p>
          <fieldset class="mt-6" :disabled="safety.loading" aria-describedby="safety-changes-hint">
            <legend class="font-bold">For Request changes: what needs changing (optional)</legend>
            <p id="safety-changes-hint" class="mt-2 text-sm">Tick the venues and equipment your comment is about, so the coordinator knows what to revise.</p>
            <label v-for="venue in review.venues" :key="venue.booking_id" class="mt-3 flex items-start gap-3"><input v-model="bookingIds" type="checkbox" :value="venue.booking_id" class="mt-1" />{{ venue.venue_name }}</label>
            <label v-for="line in review.equipment_lines" :key="line.id" class="mt-3 flex items-start gap-3"><input v-model="equipmentIds" type="checkbox" :value="line.id" class="mt-1" />{{ line.equipment_name }}</label>
          </fieldset>
          <fieldset class="mt-6" :disabled="safety.loading" aria-describedby="safety-reject-hint">
            <legend class="font-bold">For Reject: venue that fails the safety check (required)</legend>
            <p id="safety-reject-hint" class="mt-2 text-sm">Choose one venue. Only approved bookings can be rejected; the event goes back to Planning.</p>
            <label v-for="venue in review.venues" :key="venue.booking_id" class="mt-3 flex items-start gap-3">
              <input v-model="rejectedBookingId" type="radio" name="rejected-venue" :value="venue.booking_id" :disabled="venue.booking_status !== 'approved'" class="mt-1" />{{ venue.venue_name }}
            </label>
          </fieldset>
          <p v-if="!complete" class="mt-6 font-bold">{{ missingText }}</p>
          <p v-if="concern" class="mt-2 text-sm font-medium">Approval isn't available while a factor is marked Concern. Request changes or reject instead.</p>
          <div class="mt-6 flex flex-wrap gap-3">
            <BauhausButton variant="secondary" aria-label="Approve" :disabled="safety.loading || !approvable" @click="pendingKind = 'approve'">Approve</BauhausButton>
            <BauhausButton variant="yellow" aria-label="Request changes" :disabled="safety.loading || !complete || !hasComment" @click="pendingKind = 'requestChanges'">Request changes</BauhausButton>
            <BauhausButton variant="primary" aria-label="Reject" :disabled="safety.loading || !complete || !hasComment || !rejectedBookingId" @click="pendingKind = 'reject'">Reject</BauhausButton>
          </div>
        </BauhausCard>
      </div>
    </template>
    <ConfirmModal :open="!!pendingKind" :title="confirmation?.title" :message="confirmation?.message" :confirm-label="confirmation?.label" cancel-label="Cancel" @confirm="confirmDecision" @stay="pendingKind = null" />
  </main>
</template>
