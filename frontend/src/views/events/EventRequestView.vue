<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { useRouter } from "vue-router";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausCheckboxGroup from "@/components/common/BauhausCheckboxGroup.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import BauhausSelect from "@/components/common/BauhausSelect.vue";
import { FACILITIES, LAYOUTS, emptyEvent, useEventsStore } from "@/stores/events";

const router = useRouter();
const route = useRoute();
const eventsStore = useEventsStore();
const form = reactive(emptyEvent());
const fieldErrors = ref({});
const intent = ref("draft");
const isNew = computed(() => !form.id);

function validateSubmission() {
  const errors = {};
  if (!form.name.trim()) errors.name = "Enter an event title.";
  else if (form.name.trim().length < 3) errors.name = "Use at least 3 characters.";
  if (intent.value === "submit") {
    if (!form.purpose.trim()) errors.purpose = "Enter the event purpose.";
    if (!form.date) errors.date = "Enter the event date.";
    if (!form.startTime) errors.startTime = "Enter the start time.";
    if (!form.endTime) errors.endTime = "Enter the end time.";
    if (form.startTime && form.endTime && form.endTime <= form.startTime) {
      errors.endTime = "End time must be after the start time.";
    }
    if (!form.expectedAttendance || Number(form.expectedAttendance) < 1) {
      errors.expectedAttendance = "Enter expected attendance of at least 1.";
    }
    if (!form.layoutPreference) errors.layoutPreference = "Choose a layout.";
  }
  fieldErrors.value = errors;
  return Object.keys(errors).length === 0;
}

async function save() {
  if (!validateSubmission()) return;
  try {
    const event = isNew.value
      ? await eventsStore.saveDraft(form)
      : intent.value === "submit"
        ? await eventsStore.submit(form.id, form)
        : await eventsStore.updateDraft(form.id, form);
    if (intent.value === "submit") {
      await router.push({ name: "dashboard-organiser" });
    } else if (isNew.value) {
      Object.assign(form, event);
      fieldErrors.value = {};
    }
  } catch {
    // The store exposes the API message in the form alert.
  }
}

function chooseIntent(nextIntent) {
  intent.value = nextIntent;
  save();
}

onMounted(async () => {
  try {
    if (!eventsStore.events.length) await eventsStore.load();
  } catch {
    return;
  }
  const draft = eventsStore.events.find((event) => event.id === route.query.id && event.status === "draft");
  if (draft) Object.assign(form, draft);
});
</script>

<template>
  <main class="mx-auto max-w-6xl px-4 py-12 sm:px-8">
    <BauhausCard background="yellow" accent="square" accent-color="bauhaus-red" class="mb-10">
      <p class="text-xs font-bold uppercase tracking-widest opacity-80">Event request</p>
      <h1 class="mt-2 text-4xl font-black uppercase leading-[0.9] tracking-tighter sm:text-5xl">
        {{ isNew ? "Start an event" : "Edit your draft" }}
      </h1>
      <p class="mt-3 max-w-xl text-sm font-medium">
        Save the request as a draft while details are taking shape, or submit it once the required planning information is ready.
      </p>
    </BauhausCard>

    <p
      v-if="eventsStore.error"
      role="alert"
      class="mb-6 border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
    >
      {{ eventsStore.error }}
    </p>

    <form class="grid gap-8 lg:grid-cols-[1.35fr_0.65fr]" @submit.prevent="chooseIntent('submit')">
      <BauhausCard background="white" accent="none">
        <div class="grid gap-6 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <BauhausInput v-model="form.name" label="Event title" :error="fieldErrors.name" placeholder="Regional planning workshop" />
          </div>
          <div class="sm:col-span-2">
            <BauhausInput v-model="form.purpose" label="Purpose" :error="fieldErrors.purpose" placeholder="What is this event for?" />
          </div>
          <div class="sm:col-span-2 flex flex-col gap-2">
            <label for="event-description" class="text-xs font-bold uppercase tracking-widest">Description</label>
            <textarea id="event-description" v-model="form.description" rows="4" class="border-2 border-ink bg-canvas px-4 py-3 text-base font-medium shadow-hard outline-none focus:bg-bauhaus-yellow/20 sm:border-4" placeholder="Add useful context for the planning team."></textarea>
          </div>
          <BauhausInput v-model="form.date" label="Event date" type="date" :error="fieldErrors.date" />
          <BauhausInput v-model="form.expectedAttendance" label="Expected attendance" type="number" :error="fieldErrors.expectedAttendance" />
          <BauhausInput v-model="form.startTime" label="Start time" type="time" :error="fieldErrors.startTime" />
          <BauhausInput v-model="form.endTime" label="End time" type="time" :error="fieldErrors.endTime" />
          <div :class="fieldErrors.layoutPreference ? 'rounded-none border-2 border-bauhaus-red p-2' : ''">
            <BauhausSelect v-model="form.layoutPreference" label="Preferred layout" :options="LAYOUTS" placeholder="Choose a layout" />
            <p v-if="fieldErrors.layoutPreference" class="mt-2 text-xs font-bold uppercase tracking-wide text-bauhaus-red">{{ fieldErrors.layoutPreference }}</p>
          </div>
          <div class="sm:col-span-2">
            <BauhausCheckboxGroup v-model="form.facilitiesRequired" label="Facilities required" :options="FACILITIES" />
          </div>
          <div class="sm:col-span-2">
            <BauhausInput v-model="form.accessibilityNeeds" label="Accessibility needs" placeholder="Step-free access, hearing loop, etc." />
          </div>
          <div class="sm:col-span-2">
            <BauhausInput v-model="form.preliminaryEquipmentNeeds" label="Preliminary equipment needs" placeholder="Wireless microphones, projector, etc." />
          </div>
        </div>
      </BauhausCard>

      <aside class="flex flex-col gap-6">
        <BauhausCard background="white" accent="none">
          <p class="text-xs font-bold uppercase tracking-widest text-ink/70">Workflow</p>
          <p class="mt-2 text-sm font-medium">Drafts stay private to you. Submission sends a complete request for coordinator review.</p>
          <div class="mt-6 flex flex-col gap-3">
            <BauhausButton type="button" variant="yellow" :disabled="eventsStore.isSaving" @click="chooseIntent('draft')">
              {{ eventsStore.isSaving ? "Saving..." : "Save draft" }}
            </BauhausButton>
            <BauhausButton type="submit" variant="primary" :disabled="eventsStore.isSaving">Submit request</BauhausButton>
            <BauhausButton type="button" variant="outline" :disabled="eventsStore.isSaving" @click="router.push({ name: 'dashboard-organiser' })">Cancel</BauhausButton>
          </div>
        </BauhausCard>
      </aside>
    </form>
  </main>
</template>
