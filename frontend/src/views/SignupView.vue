<script setup>
import { ref, toRef } from "vue";
import { useRoute, useRouter } from "vue-router";

import AuthPageLayout from "@/components/common/AuthPageLayout.vue";
import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausCard from "@/components/common/BauhausCard.vue";
import BauhausInput from "@/components/common/BauhausInput.vue";
import { ApiError, authApi } from "@/services/api";

// Sign-up creates no session, so it calls the API directly rather than
// through the auth store (SCRUM-80/83). The route fixes the account role.
const props = defineProps({
  role: { type: String, required: true },
});

const role = toRef(props, "role");
const form = ref({
  full_name: "",
  email: "",
  password: "",
  organisation_name: "",
  phone_number: "",
});
const fieldErrors = ref({});
const formError = ref("");
const isSubmitting = ref(false);

const REQUIRED_FIELDS = {
  full_name: "Full name is required.",
  email: "Email is required.",
  password: "Password is required.",
};

// A shape check only; the backend's EmailStr is the authority.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// Mirrors the backend's PASSWORD_MIN_LENGTH / PASSWORD_RULE in
// auth/schemas.py (ACC-R8); change both together.
const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_RULE = "Password must be at least 8 characters and include at least one letter and one digit.";

function meetsPasswordRule(password) {
  return password.length >= PASSWORD_MIN_LENGTH && /\p{L}/u.test(password) && /\p{Nd}/u.test(password);
}

function validate() {
  const errors = {};
  for (const [name, message] of Object.entries(REQUIRED_FIELDS)) {
    if (!form.value[name].trim()) errors[name] = message;
  }
  if (role.value === "event_organiser" && !form.value.organisation_name.trim()) {
    errors.organisation_name = "Organisation name is required.";
  }
  if (!errors.email && !EMAIL_PATTERN.test(form.value.email.trim())) {
    errors.email = "Enter a valid email address.";
  }
  if (!errors.password && !meetsPasswordRule(form.value.password)) {
    errors.password = PASSWORD_RULE;
  }
  fieldErrors.value = errors;
  return Object.keys(errors).length === 0;
}

// A 422's `detail[]` entries each name a field as `loc: ["body", <field>]`.
function serverFieldErrors(detail) {
  const errors = {};
  for (const { loc, msg } of detail) {
    const name = loc?.[loc.length - 1];
    if (name in form.value && !errors[name]) errors[name] = msg;
  }
  return errors;
}

const router = useRouter();
const route = useRoute();

async function handleSubmit() {
  if (!validate()) return;

  formError.value = "";
  isSubmitting.value = true;
  try {
    const details = {
      role: role.value,
      full_name: form.value.full_name,
      email: form.value.email.trim(),
      password: form.value.password,
    };
    if (role.value === "event_organiser") {
      details.organisation_name = form.value.organisation_name;
      // Optional: an unfilled field means no phone number, not "".
      details.phone_number = form.value.phone_number.trim() || null;
    }
    await authApi.signup(details);
    // History state, not the query string, so the email stays out of the URL.
    router.push({
      name: "login",
      query: route.query.redirect ? { redirect: route.query.redirect } : {},
      state: { signedUpEmail: form.value.email },
    });
  } catch (error) {
    if (error.status === 409) fieldErrors.value = { email: error.message };
    else if (error.status === 422 && Array.isArray(error.detail)) fieldErrors.value = serverFieldErrors(error.detail);
    else if (error instanceof ApiError) formError.value = error.message;
    else formError.value = "Could not create your account. Please try again.";
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <AuthPageLayout>
    <BauhausCard background="white" accent="square" accent-color="bauhaus-blue">
      <form class="flex flex-col gap-6" novalidate @submit.prevent="handleSubmit">
        <div>
          <h2 class="text-2xl font-bold">
            {{ role === "attendee" ? "Create an Attendee Account" : "Create an Event Organiser Account" }}
          </h2>
          <p class="mt-1 text-sm font-medium text-ink/70">
            {{ role === "attendee" ? "Sign up as an Attendee to use ConnectSphere." : "Sign up as an Event Organiser to request events." }}
          </p>
        </div>

        <div
          v-if="formError"
          role="alert"
          class="border-2 border-ink bg-bauhaus-red px-4 py-3 text-sm font-bold text-canvas shadow-hard sm:border-4"
        >
          {{ formError }}
        </div>

        <BauhausInput
          v-model="form.full_name"
          :error="fieldErrors.full_name"
          label="Full name"
          required
          autocomplete="name"
        />
        <BauhausInput
          v-model="form.email"
          :error="fieldErrors.email"
          label="Email"
          type="email"
          required
          placeholder="you@example.com"
          autocomplete="email"
        />
        <BauhausInput
          v-model="form.password"
          :error="fieldErrors.password"
          label="Password"
          type="password"
          required
          placeholder="••••••••"
          autocomplete="new-password"
        />
        <BauhausInput
          v-if="role === 'event_organiser'"
          v-model="form.organisation_name"
          :error="fieldErrors.organisation_name"
          label="Organisation name"
          required
          autocomplete="organization"
        />
        <BauhausInput
          v-if="role === 'event_organiser'"
          v-model="form.phone_number"
          :error="fieldErrors.phone_number"
          label="Phone number"
          type="tel"
          autocomplete="tel"
        />

        <BauhausButton type="submit" variant="primary" full-width :disabled="isSubmitting">
          {{ isSubmitting ? "Creating Account…" : "Create Account" }}
        </BauhausButton>
      </form>
    </BauhausCard>
  </AuthPageLayout>
</template>
