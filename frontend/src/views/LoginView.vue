<script setup>
import { ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import AuthPageLayout from "@/components/common/AuthPageLayout.vue";
import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import { useAuthStore } from "@/stores/auth";

// Set by SignupView after a successful sign-up (SCRUM-80).
const signedUpEmail = window.history.state?.signedUpEmail ?? "";

const email = ref(signedUpEmail);
const password = ref("");
const fieldErrors = ref({ email: "", password: "" });

const authStore = useAuthStore();
const router = useRouter();
const route = useRoute();

function validate() {
  fieldErrors.value = { email: "", password: "" };
  let isValid = true;

  if (!email.value) {
    fieldErrors.value.email = "Email is required.";
    isValid = false;
  }
  if (!password.value) {
    fieldErrors.value.password = "Password is required.";
    isValid = false;
  }
  return isValid;
}

async function handleSubmit() {
  if (!validate()) return;

  try {
    await authStore.login(email.value, password.value);
    const redirectTarget = route.query.redirect;
    router.push(redirectTarget || authStore.dashboardPath);
  } catch {
    // authStore.error already holds a user-facing message.
  }
}
</script>

<template>
  <AuthPageLayout>
    <BauhausCard background="white" accent="square" accent-color="bauhaus-red">
      <form class="flex flex-col gap-6" novalidate @submit.prevent="handleSubmit">
        <h2 class="text-2xl font-black uppercase tracking-tight">Sign In</h2>

        <div
          v-if="signedUpEmail && !authStore.error"
          role="status"
          class="border-2 border-ink bg-bauhaus-yellow px-4 py-3 text-sm font-bold uppercase tracking-wide text-ink shadow-hard sm:border-4"
        >
          Account created. Please sign in.
        </div>

        <div
          v-if="authStore.error"
          role="alert"
          class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold uppercase tracking-wide text-canvas shadow-hard sm:border-4"
        >
          {{ authStore.error }}
        </div>

        <BauhausInput
          v-model="email"
          label="Email"
          type="email"
          placeholder="you@example.com"
          autocomplete="username"
          :error="fieldErrors.email"
        />
        <BauhausInput
          v-model="password"
          label="Password"
          type="password"
          placeholder="••••••••"
          autocomplete="current-password"
          :error="fieldErrors.password"
        />

        <BauhausButton type="submit" variant="primary" full-width :disabled="authStore.isLoading">
          {{ authStore.isLoading ? "Signing In…" : "Sign In" }}
        </BauhausButton>

        <div class="flex flex-col gap-2 border-t-2 border-ink pt-4 text-center text-sm font-medium text-ink/70">
          <p>
            New Event Organiser?
            <RouterLink to="/signup/organiser" class="font-bold uppercase tracking-wide text-bauhaus-blue underline">
              Create organiser account
            </RouterLink>
          </p>
          <p>
            New Attendee?
            <RouterLink to="/signup/attendee" class="font-bold uppercase tracking-wide text-bauhaus-blue underline">
              Create attendee account
            </RouterLink>
          </p>
        </div>
      </form>
    </BauhausCard>
  </AuthPageLayout>
</template>
