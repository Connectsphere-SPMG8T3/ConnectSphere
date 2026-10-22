<script setup>
import { computed } from "vue";
import { RouterLink } from "vue-router";

import BauhausCard from "@/components/common/BauhausCard.vue";
import { ROLE_LABELS, useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const profile = computed(() => authStore.profile);

const roleLabel = computed(() => ROLE_LABELS[profile.value?.role] ?? profile.value?.role);
const allRoleLabels = computed(() => authStore.roles.map((role) => ROLE_LABELS[role] ?? role));
</script>

<template>
  <main class="py-8">
    <h1 class="mb-8 text-4xl font-bold leading-tight sm:text-5xl">My profile</h1>

    <BauhausCard v-if="profile" background="white" accent="circle" accent-color="bauhaus-blue">
      <div class="flex flex-col gap-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <h2 class="text-2xl font-bold">{{ profile.full_name }}</h2>
          <span class="border-2 border-ink bg-bauhaus-yellow px-3 py-1 text-xs font-bold sm:border-4">
            {{ roleLabel }}
          </span>
        </div>

        <dl class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt class="text-xs font-bold text-ink/60">Email</dt>
            <dd class="text-base font-medium">{{ profile.email }}</dd>
          </div>
          <div v-if="profile.organisation_name">
            <dt class="text-xs font-bold text-ink/60">Organisation</dt>
            <dd class="text-base font-medium">{{ profile.organisation_name }}</dd>
          </div>
          <div v-if="profile.department">
            <dt class="text-xs font-bold text-ink/60">Department</dt>
            <dd class="text-base font-medium">{{ profile.department }}</dd>
          </div>
          <div v-if="profile.phone_number">
            <dt class="text-xs font-bold text-ink/60">Phone</dt>
            <dd class="text-base font-medium">{{ profile.phone_number }}</dd>
          </div>
          <div v-if="authStore.hasMultipleRoles">
            <dt class="text-xs font-bold text-ink/60">All roles</dt>
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

        <RouterLink
          :to="authStore.dashboardPath"
          class="mt-2 inline-block w-fit border-2 border-ink bg-canvas px-4 py-2 text-xs font-bold shadow-hard hover:bg-muted sm:border-4"
        >
          &larr; Back to Dashboard
        </RouterLink>
      </div>
    </BauhausCard>
  </main>
</template>
