<script setup>
// The public auth pages' frame: backdrop shapes and the ConnectSphere
// wordmark above the page's card (LoginView, SignupView).
</script>

<template>
  <main class="relative flex min-h-screen items-center justify-center overflow-hidden bg-canvas px-4 py-12">
    <div class="pointer-events-none absolute -left-16 -top-16 h-64 w-64 rounded-full bg-bauhaus-yellow/70 sm:h-80 sm:w-80" aria-hidden="true" />
    <div class="pointer-events-none absolute -bottom-20 -right-20 h-72 w-72 bg-bauhaus-blue/70 sm:h-96 sm:w-96" aria-hidden="true" />

    <div class="relative z-10 w-full max-w-md">
      <div class="mb-8 text-center">
        <h1 class="text-5xl font-black uppercase leading-[0.9] tracking-tighter text-ink sm:text-6xl">
          Connect<span class="text-bauhaus-red">Sphere</span>
        </h1>
        <p class="mt-3 text-sm font-bold uppercase tracking-widest text-ink/70">
          Event &amp; Venue Services Platform
        </p>
      </div>

      <slot />
    </div>
  </main>
</template>
