<script setup lang="ts">
import BattlefieldMap from '@/components/map/BattlefieldMap.vue';
import SideBar from '@/layouts/SideBar.vue';
</script>
<template>
    <div class="flex h-full">
        <BattlefieldMap class="flex-1 bg-gray-200" />
        <SideBar class="w-64 bg-white" />
    </div>
</template>