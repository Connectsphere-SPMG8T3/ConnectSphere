<script setup>
import { computed, ref, watch } from "vue";

import BauhausButton from "@/components/common/BauhausButton.vue";
import BauhausEmptyState from "@/components/common/BauhausEmptyState.vue";
import { canPost, COMMENT_MAX_LENGTH, validateComment } from "@/features/events/comments";
import { useEventCommentsStore } from "@/features/events/eventCommentsStore";
import { ROLE_LABELS } from "@/stores/auth";

const props = defineProps({
  eventId: { type: String, required: true },
  status: { type: String, required: true },
});

const store = useEventCommentsStore();
const draft = ref("");
const isOpen = computed(() => canPost(props.status));
const canSubmit = computed(() => !validateComment(draft.value) && !store.isPosting);

const formatter = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Singapore",
});

watch(
  () => props.eventId,
  (eventId) => {
    draft.value = "";
    store.load(eventId);
  },
  { immediate: true },
);

async function submit() {
  if (!canSubmit.value) return;
  if (await store.post(draft.value)) draft.value = "";
}
</script>

<template>
  <section aria-labelledby="discussion-title">
    <h2 id="discussion-title" class="mb-6 text-2xl font-black uppercase tracking-tight">Discussion</h2>

    <p v-if="store.isLoading && !store.comments.length" class="text-sm font-bold uppercase tracking-widest text-ink/70">
      Loading comments…
    </p>
    <BauhausEmptyState
      v-else-if="!store.comments.length"
      title="No comments yet"
      :detail="isOpen ? 'Questions and planning notes for this event appear here.' : ''"
    />
    <ol v-else class="space-y-4">
      <li v-for="comment in store.comments" :key="comment.id" class="border-l-4 border-ink pl-4">
        <p class="text-xs font-bold text-ink/70">
          <span class="font-black uppercase tracking-wide text-ink">{{ comment.author?.full_name ?? "Unknown user" }}</span>
          <template v-if="comment.author?.role"> · {{ ROLE_LABELS[comment.author.role] ?? comment.author.role }}</template>
          · {{ formatter.format(new Date(comment.created_at)) }}
        </p>
        <p data-comment-body class="mt-1 whitespace-pre-wrap break-words text-sm font-medium">{{ comment.body }}</p>
      </li>
    </ol>

    <p
      v-if="store.error"
      role="alert"
      class="mt-4 border-2 border-ink bg-bauhaus-red px-3 py-2 text-sm font-bold text-canvas"
    >
      {{ store.error }}
    </p>

    <form v-if="isOpen" class="mt-6" @submit.prevent="submit">
      <label for="comment-body" class="block text-xs font-bold uppercase tracking-widest text-ink/70">Add a comment</label>
      <textarea
        id="comment-body"
        v-model="draft"
        rows="3"
        :maxlength="COMMENT_MAX_LENGTH"
        class="mt-2 w-full border-2 border-ink bg-canvas p-3 font-medium focus:outline-none focus:ring-4 focus:ring-bauhaus-yellow"
      ></textarea>
      <div class="mt-2 flex items-center justify-between gap-4">
        <p class="text-xs font-bold text-ink/70">{{ draft.length }} / {{ COMMENT_MAX_LENGTH }}</p>
        <BauhausButton type="submit" variant="secondary" aria-label="Post comment" :disabled="!canSubmit">
          {{ store.isPosting ? "Posting…" : "Post" }}
        </BauhausButton>
      </div>
    </form>
    <p v-else class="mt-6 text-sm font-medium text-ink/70">This discussion is closed. Earlier comments stay on the record.</p>
  </section>
</template>
