<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import SafetyDecisionDetails from "@/components/events/SafetyDecisionDetails.vue";
import ConfirmModal from "@/components/common/ConfirmModal.vue";
import { showToast } from "@/composables/useToast";
import { exitConfirmationText } from "@/features/equipment/technical";
import { displaySafetyTime } from "@/features/events/safetyDecision";
import { useSafetyDecisionStore } from "@/features/events/safetyDecisionStore";

const route = useRoute();
const router = useRouter();
const safety = useSafetyDecisionStore();
const comment = ref("");
const bookingIds = ref([]);
const rejectedBookingId = ref(null);
const equipmentIds = ref([]);
const pendingKind = ref(null);
const review = computed(() => safety.review);
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
  const text = comment.value.trim();
  const payload = kind === "approve" ? { comment: text || null } : kind === "reject" ? { reason: text, booking_id: rejectedBookingId.value } : {
    comment: text,
    booking_ids: [...bookingIds.value], equipment_request_ids: [...equipmentIds.value],
  };
  try {
    await safety.decide(kind, route.params.id, payload);
    comment.value = "";
    bookingIds.value = [];
    equipmentIds.value = [];
    rejectedBookingId.value = null;
    showToast(confirmations[kind].toast);
    await router.push({ name: "dashboard-safety" });
  } catch {
    // The API's refusal is shown in the page alert.
  }
}
watch(() => route.params.id, (id) => {
  comment.value = "";
  bookingIds.value = [];
  equipmentIds.value = [];
  rejectedBookingId.value = null;
  pendingKind.value = null;
  if (id) safety.loadReview(id);
}, { immediate: true });
</script>

<template>
  <main class="break-words py-12">
    <BauhausButton variant="outline" class="mb-8" @click="router.push({ name: 'dashboard-safety' })">Back to queue</BauhausButton>
    <p v-if="safety.error" role="alert" class="mb-6 border-4 border-ink p-4 font-bold">{{ safety.error }}</p>
    <p v-if="safety.loading && !review" class="font-bold uppercase">Loading safety review…</p>
    <template v-if="review">
      <BauhausCard background="yellow" accent="none" class="mb-8">
        <h1 class="text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">{{ review.event.name }}</h1>
        <dl class="mt-6 grid gap-4 sm:grid-cols-2">
          <div><dt class="font-bold uppercase">Organiser</dt><dd>{{ review.event.organiser_name }}</dd></div>
          <div><dt class="font-bold uppercase">Coordinator</dt><dd>{{ review.event.coordinator_name ?? 'Not provided' }}</dd></div>
          <div><dt class="font-bold uppercase">Starts</dt><dd>{{ displaySafetyTime(review.event.starts_at) }}</dd></div>
          <div><dt class="font-bold uppercase">Ends</dt><dd>{{ displaySafetyTime(review.event.ends_at) }}</dd></div>
          <div><dt class="font-bold uppercase">Expected attendance</dt><dd>{{ review.event.expected_attendance ?? 'Not provided' }}</dd></div>
          <div><dt class="font-bold uppercase">Accessibility needs</dt><dd>{{ review.event.accessibility_needs || 'None specified' }}</dd></div>
        </dl>
      </BauhausCard>
      <div class="grid min-w-0 gap-8 lg:grid-cols-2">
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-black uppercase">Venues</h2>
          <div v-for="venue in review.venues" :key="venue.booking_id" class="mt-6 border-t-2 border-ink pt-4">
            <h3 class="text-xl font-black uppercase">{{ venue.venue_name }}</h3>
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
          <h2 class="text-2xl font-black uppercase">Equipment</h2>
          <p v-if="!review.equipment_lines.length" class="mt-4">No equipment requested</p>
          <ul v-else class="mt-4 space-y-3"><li v-for="line in review.equipment_lines" :key="line.id">{{ line.equipment_name }} × {{ line.quantity }} — {{ line.status }}</li></ul>
          <p class="mt-6 font-bold">Exit confirmation</p><p v-if="review.exit_confirmation">Equipment does not block exits or walkways.</p><p>{{ exitConfirmationText(review.exit_confirmation) }}</p>
        </BauhausCard>
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-black uppercase">Registration — for information</h2>
          <p class="mt-4">{{ review.event.registration.enabled ? 'Enabled' : 'Not enabled' }}</p>
          <dl v-if="review.event.registration.enabled" class="mt-3 grid gap-3">
            <div><dt class="font-bold">Capacity</dt><dd>{{ review.event.registration.capacity ?? 'Not provided' }}</dd></div>
            <div><dt class="font-bold">Opens</dt><dd>{{ displaySafetyTime(review.event.registration.opens_at) }}</dd></div>
            <div><dt class="font-bold">Closes</dt><dd>{{ displaySafetyTime(review.event.registration.closes_at) }}</dd></div>
          </dl>
        </BauhausCard>
        <BauhausCard background="white" accent="none">
          <h2 class="text-2xl font-black uppercase">Earlier safety decisions</h2>
          <p v-if="!safety.decisions.length" class="mt-4">No earlier safety decisions</p>
          <ul v-else class="mt-4 space-y-4">
            <li v-for="decision in safety.decisions" :key="decision.id">
              <SafetyDecisionDetails :decision="decision" />
            </li>
          </ul>
        </BauhausCard>
        <BauhausCard background="white" accent="none" class="lg:col-span-2">
          <h2 class="text-2xl font-black uppercase">Safety decision</h2>
          <label for="safety-comment" class="mt-6 block font-bold uppercase">Comment</label>
          <textarea id="safety-comment" v-model="comment" maxlength="1000" rows="5" aria-describedby="safety-comment-hint" class="mt-2 w-full border-2 border-ink bg-canvas p-3" :disabled="safety.loading" />
          <p id="safety-comment-hint" class="mt-2 text-sm">Required to request changes or reject. Note any crowd-movement concerns here.</p>
          <fieldset class="mt-6" :disabled="safety.loading" aria-describedby="safety-changes-hint">
            <legend class="font-bold uppercase">For Request changes: what needs changing (optional)</legend>
            <p id="safety-changes-hint" class="mt-2 text-sm">Tick the venues and equipment your comment is about, so the coordinator knows what to revise.</p>
            <label v-for="venue in review.venues" :key="venue.booking_id" class="mt-3 flex items-start gap-3"><input v-model="bookingIds" type="checkbox" :value="venue.booking_id" class="mt-1" />{{ venue.venue_name }}</label>
            <label v-for="line in review.equipment_lines" :key="line.id" class="mt-3 flex items-start gap-3"><input v-model="equipmentIds" type="checkbox" :value="line.id" class="mt-1" />{{ line.equipment_name }}</label>
          </fieldset>
          <fieldset class="mt-6" :disabled="safety.loading" aria-describedby="safety-reject-hint">
            <legend class="font-bold uppercase">For Reject: venue that fails the safety check (required)</legend>
            <p id="safety-reject-hint" class="mt-2 text-sm">Choose one venue. Only approved bookings can be rejected; the event goes back to Planning.</p>
            <label v-for="venue in review.venues" :key="venue.booking_id" class="mt-3 flex items-start gap-3">
              <input v-model="rejectedBookingId" type="radio" name="rejected-venue" :value="venue.booking_id" :disabled="venue.booking_status !== 'approved'" class="mt-1" />{{ venue.venue_name }}
            </label>
          </fieldset>
          <div class="mt-6 flex flex-wrap gap-3">
            <BauhausButton variant="secondary" aria-label="Approve" :disabled="safety.loading" @click="pendingKind = 'approve'">Approve</BauhausButton>
            <BauhausButton variant="yellow" aria-label="Request changes" :disabled="safety.loading || !comment.trim()" @click="pendingKind = 'requestChanges'">Request changes</BauhausButton>
            <BauhausButton variant="primary" aria-label="Reject" :disabled="safety.loading || !comment.trim() || !rejectedBookingId" @click="pendingKind = 'reject'">Reject</BauhausButton>
          </div>
        </BauhausCard>
      </div>
    </template>
    <ConfirmModal :open="!!pendingKind" :title="confirmation?.title" :message="confirmation?.message" :confirm-label="confirmation?.label" cancel-label="Cancel" @confirm="confirmDecision" @stay="pendingKind = null" />
  </main>
</template>
