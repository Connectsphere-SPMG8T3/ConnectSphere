<script setup>
import { computed, ref } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import { serverFieldErrors } from "@/features/auth/fieldErrors";
import {
  formatSingaporePhoneNumber,
  normalizeSingaporePhoneNumber,
  singaporePhoneError,
} from "@/features/auth/phoneNumber";
import { ApiError } from "@/services/api";
import { ROLE_LABELS, useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const profile = computed(() => authStore.profile);
const isEditing = ref(false);
const isSaving = ref(false);
const draft = ref({ full_name: "", phone_number: "" });
const fieldErrors = ref({});
const formError = ref("");

const roleLabel = computed(() => ROLE_LABELS[profile.value?.role] ?? profile.value?.role);
const initials = computed(() =>
  (profile.value?.full_name ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join(""),
);
const allRoleLabels = computed(() => authStore.roles.map((role) => ROLE_LABELS[role] ?? role));

function startEditing() {
  draft.value = {
    full_name: profile.value.full_name,
    phone_number: formatSingaporePhoneNumber(profile.value.phone_number) ?? "",
  };
  fieldErrors.value = {};
  formError.value = "";
  isEditing.value = true;
}

function cancelEditing() {
  isEditing.value = false;
  fieldErrors.value = {};
  formError.value = "";
}

async function saveProfile() {
  fieldErrors.value = {};
  formError.value = "";
  if (!draft.value.full_name.trim()) {
    fieldErrors.value = { full_name: "Full name is required." };
    return;
  }
  const phoneError = singaporePhoneError(draft.value.phone_number);
  if (phoneError) {
    fieldErrors.value = { phone_number: phoneError };
    return;
  }

  isSaving.value = true;
  try {
    await authStore.updateProfile({
      full_name: draft.value.full_name.trim(),
      phone_number: normalizeSingaporePhoneNumber(draft.value.phone_number),
    });
    isEditing.value = false;
  } catch (error) {
    if (error instanceof ApiError && error.status === 422 && Array.isArray(error.detail)) {
      fieldErrors.value = serverFieldErrors(error.detail, draft.value);
      if (Object.keys(fieldErrors.value).length === 0) formError.value = error.message;
    } else if (error instanceof ApiError) {
      formError.value = error.message;
    } else {
      formError.value = "Could not update your profile. Please try again.";
    }
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <main class="py-8">
    <h1 class="mb-8 text-4xl font-bold leading-tight sm:text-5xl">My profile</h1>

    <BauhausCard v-if="profile" background="white" accent="none">
      <div class="flex flex-col gap-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-center gap-4">
            <span
              class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-2 border-ink bg-bauhaus-blue text-lg font-bold text-canvas sm:h-16 sm:w-16 sm:border-4 sm:text-xl"
              aria-hidden="true"
            >
              {{ initials }}
            </span>
            <div class="flex flex-col items-start gap-2">
              <h2 class="text-2xl font-bold leading-tight">{{ profile.full_name }}</h2>
              <span class="border-2 border-ink bg-bauhaus-yellow px-3 py-1 text-xs font-bold">
                {{ roleLabel }}
              </span>
            </div>
          </div>
          <BauhausButton v-if="!isEditing" size="sm" variant="outline" @click="startEditing">
            Edit profile
          </BauhausButton>
        </div>

        <form v-if="isEditing" class="flex flex-col gap-5 border-t-2 border-ink pt-6" novalidate @submit.prevent="saveProfile">
          <div
            v-if="formError"
            role="alert"
            class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
          >
            {{ formError }}
          </div>
          <BauhausInput
            v-model="draft.full_name"
            :error="fieldErrors.full_name"
            label="Full name"
            required
            autocomplete="name"
          />
          <BauhausInput
            v-model="draft.phone_number"
            :error="fieldErrors.phone_number"
            label="Phone number"
            type="tel"
            autocomplete="tel"
          />
          <div class="flex flex-wrap gap-3">
            <BauhausButton type="submit" :disabled="isSaving">
              {{ isSaving ? "Saving…" : "Save changes" }}
            </BauhausButton>
            <BauhausButton type="button" variant="outline" :disabled="isSaving" @click="cancelEditing">
              Cancel
            </BauhausButton>
          </div>
        </form>

        <dl v-else class="grid grid-cols-1 gap-4 border-t-2 border-ink pt-6 sm:grid-cols-2">
          <div>
            <dt class="text-sm font-medium text-ink/60">Email</dt>
            <dd class="text-base font-medium">{{ profile.email }}</dd>
          </div>
          <div v-if="profile.organisation_name">
            <dt class="text-sm font-medium text-ink/60">Organisation</dt>
            <dd class="text-base font-medium">{{ profile.organisation_name }}</dd>
          </div>
          <div v-if="profile.department">
            <dt class="text-sm font-medium text-ink/60">Department</dt>
            <dd class="text-base font-medium">{{ profile.department }}</dd>
          </div>
          <div>
            <dt class="text-sm font-medium text-ink/60">Phone</dt>
            <dd class="text-base font-medium">
              {{ formatSingaporePhoneNumber(profile.phone_number) || "Not provided" }}
            </dd>
          </div>
          <div v-if="authStore.hasMultipleRoles">
            <dt class="text-sm font-medium text-ink/60">All roles</dt>
            <dd class="mt-1 flex flex-wrap gap-2">
              <span
                v-for="label in allRoleLabels"
                :key="label"
                class="border-2 border-ink bg-canvas px-2 py-0.5 text-xs font-bold"
              >
                {{ label }}
              </span>
            </dd>
          </div>
        </dl>
      </div>
    </BauhausCard>
  </main>
</template>
