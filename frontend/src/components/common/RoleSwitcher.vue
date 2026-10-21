<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";

import BauhausSelect from "@/components/common/BauhausSelect.vue";
import { ROLE_LABELS, useAuthStore } from "@/stores/auth";

// The "Acting as" switcher for an account holding several roles (SCRUM-74/75).
// It sits in the top bar on wider screens and in the slide-out menu on phones;
// only one copy is ever rendered.
defineProps({
  // The top bar's form: one box the bell's height reading "Role: <role>",
  // instead of the labelled BauhausSelect the menu uses.
  compact: { type: Boolean, default: false },
});

const authStore = useAuthStore();
const router = useRouter();

const roleOptions = computed(() =>
  authStore.roles.map((role) => ({ value: role, label: ROLE_LABELS[role] ?? role })),
);

// BauhausSelect binds its native <select> with a plain :value/@change pair
// (not v-model), so the browser sets the visible selection imperatively the
// instant the user picks an option, before this handler even runs. When the
// switch is a no-op or fails, authStore.role never changes — nothing
// reactive fires — so nothing corrects that DOM value on its own; bumping
// this key forces BauhausSelect to remount and re-apply the current role.
// Only bumped on those two paths: a successful switch already changes
// authStore.role for real, so Vue's normal reactivity updates the select
// correctly without a remount — bumping unconditionally would remount (and
// flicker) on every switch, not just the ones that need correcting.
const roleSwitcherKey = ref(0);

async function handleRoleChange(role) {
  // BauhausSelect always renders an empty placeholder option, and re-selecting
  // the already-active role should be a no-op rather than a round-trip.
  if (!role || role === authStore.role) {
    roleSwitcherKey.value += 1;
    return;
  }
  try {
    await authStore.setActiveRole(role);
    await router.push(authStore.dashboardPath);
  } catch {
    // Switch rejected (e.g. role no longer held): authStore.role is
    // unchanged, so force the remount to redisplay it correctly.
    roleSwitcherKey.value += 1;
  }
}
</script>

<template>
  <div v-if="authStore.hasMultipleRoles" data-testid="role-switcher">
    <!-- The visible "Role:" is part of the accessible name, which still starts
         "Acting as" so screen readers and the browser tests find it the same way. -->
    <label
      v-if="compact"
      class="flex h-10 cursor-pointer items-center gap-1 border-2 border-ink bg-bauhaus-yellow pl-3 pr-2 text-sm font-bold text-ink shadow-hard transition-colors hover:bg-muted has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink"
    >
      <span aria-hidden="true">Role:</span>
      <select
        :key="roleSwitcherKey"
        aria-label="Acting as role"
        :value="authStore.role"
        class="h-full min-w-0 cursor-pointer bg-transparent font-bold outline-none"
        @change="handleRoleChange($event.target.value)"
      >
        <option v-for="option in roleOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    </label>
    <BauhausSelect
      v-else
      :key="roleSwitcherKey"
      label="Acting as"
      :model-value="authStore.role"
      :options="roleOptions"
      placeholder="Select a role"
      @update:model-value="handleRoleChange"
    />
  </div>
</template>
