<script setup>
// The public auth pages' frame (LoginView, SignupView): the shared public
// header and footer around the page's card, with a decorative panel beside
// it where a speech bubble types out `greeting` above an illustration.
// The header carries the brand, so the card's title is the page's <h1>.
import { onBeforeUnmount, onMounted, ref } from "vue";

import EventPlanIllustration from "@/components/common/EventPlanIllustration.vue";
import PublicFooter from "@/components/common/PublicFooter.vue";
import PublicHeader from "@/components/common/PublicHeader.vue";
import TicketIllustration from "@/components/common/TicketIllustration.vue";
import { useMediaQuery } from "@/composables/useMediaQuery";

const props = defineProps({
  greeting: { type: String, required: true },
  illustration: {
    type: String,
    default: "ticket",
    validator: (value) => ["ticket", "plan"].includes(value),
  },
});

const TYPE_MS = 45;

const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)", true);
const typed = ref(props.greeting);
let timer = null;

onMounted(() => {
  if (reduceMotion.value) return;
  typed.value = "";
  timer = setInterval(() => {
    typed.value = props.greeting.slice(0, typed.value.length + 1);
    if (typed.value === props.greeting) clearInterval(timer);
  }, TYPE_MS);
});
onBeforeUnmount(() => clearInterval(timer));
</script>

<template>
  <div class="flex min-h-screen flex-col bg-canvas text-ink">
    <!-- No account actions in the header: the card is the action. -->
    <PublicHeader />

    <main class="flex flex-1 items-center justify-center px-4 py-12 sm:px-10">
      <div class="grid w-full max-w-5xl grid-cols-1 gap-8 md:grid-cols-2">
        <!-- A one-cell grid stretches the card to the panel's height. -->
        <div class="grid min-w-0">
          <slot />
        </div>

        <!-- Decorative only: the form beside it carries everything a reader needs. -->
        <div
          data-testid="auth-illustration"
          class="hidden flex-col items-center justify-center gap-10 overflow-hidden border-2 border-ink bg-bauhaus-yellow p-8 md:flex"
          aria-hidden="true"
        >
          <div class="relative w-full max-w-sm">
            <p data-testid="speech-bubble" class="min-h-16 border-4 border-ink bg-canvas px-5 py-4 text-lg font-bold leading-tight shadow-hard">{{ typed }}</p>
            <!-- The bubble's tail: a square turned on its corner, tucked under the bubble. -->
            <span class="absolute -bottom-3 left-10 h-6 w-6 rotate-45 border-b-4 border-r-4 border-ink bg-canvas"></span>
          </div>
          <EventPlanIllustration v-if="illustration === 'plan'" animated />
          <TicketIllustration v-else animated />
        </div>
      </div>
    </main>

    <PublicFooter />
  </div>
</template>
