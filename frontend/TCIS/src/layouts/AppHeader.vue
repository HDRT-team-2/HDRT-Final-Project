<script setup lang="ts">
import SendBtn from '@/components/common/SendBtn.vue';
import logo from '@/components/icons/HRLogo.vue'
import Time from '@/components/common/Time.vue'
</script>
<template>
  <header class="bg-gradient-to-r from-rotem-800 to-rotem-600 flex items-center p-2">
    <logo />
    <h1 class="text-white text-2xl flex-1 text-center">
      Tactical Command Information System
    </h1>
    <Time />
    <!-- <SendBtn /> -->
  </header>
</template>
