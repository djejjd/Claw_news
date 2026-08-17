<script setup lang="ts">
import { computed } from "vue";

import { toSafeExternalUrl } from "../api/externalUrl";

const props = defineProps({
  url: { type: String, required: true },
});

const safeUrl = computed(() => toSafeExternalUrl(props.url));
</script>

<template>
  <a
    v-if="safeUrl"
    :href="safeUrl"
    target="_blank"
    rel="noopener noreferrer"
  >
    <slot />
  </a>
  <span v-else><slot /></span>
</template>
