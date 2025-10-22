<script setup lang="ts">
import BattlefieldMap from '@/components/map/BattlefieldMap.vue';
import SideBar from '@/layouts/SideBar.vue';

const leftsidebar= {
    contents: [
        'StatusReport',
        'SituationLog'
    ],
    col: [2,10]
}
const rightsidebar= {
    contents: [
        'PositionInfo',
        'TargetInput',
        'DetectedObjects',
        'FireSchedule',
    ],
    col: [1,1,4,3]
}
</script>
<template>
    <div class="flex h-full">
        <SideBar class="w-64 bg-white" :contents="leftsidebar.contents" :col="leftsidebar.col" />
        <BattlefieldMap class="flex-1 bg-gray-200" />
        <SideBar class="w-64 bg-white" :contents="rightsidebar.contents" :col="rightsidebar.col" />
    </div>
</template>