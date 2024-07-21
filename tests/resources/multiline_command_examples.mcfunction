execute
    as @a
    at @s
    align xyz
    if block ~ ~ ~ #wool[
        foo = bar
    ]
    run
        summon armor_stand ~ ~ ~ {
            Tags: [
                "position_history",
                "new"
            ],
            Invisible: 1b,
            Marker: 1b
        }

execute if block 0 0 0
    #wool #this is a comment
execute if block 0 0 0 #wool #this is a comment
execute if block 0 0 0
    wool #this is a comment
execute if block 0 0 0 wool #this is a comment

execute if block
    ~ 1 -0
        #wool

tellraw @s {
    "text": "Hover me!",
    "hoverEvent": {
        "action": "show_text",
        "value": "Hi!"
    }
}

execute
    # When the player is on wool
    as @a
    at @s
    if block ~ ~-1 ~ #wool

    # Give a special stone block
    run give @s stone{
        display: {
            Name: '[{"text": "Hello", "bold": true}]',
            Lore: [
                '[{ "text": "Something else here" }]',
            ]
        }
    }

execute
    if block ~ ~ ~ #namespace:tag  # But what if # we # put # hash # symbols
    if entity @s[tag=foo] # everywhere #

tellraw @a {
    "text": "Hello # there"
}

tellraw @a  # here
    {
        "text": "Hello\" # \"there"
    }

tellraw @s ["foo"]  # thing

say
    foo
    bar
    hello
 wat
    welp

say
    this
    is a
    # some comment
    continuation

gamerule
    doDaylightCycle
 false

gamerule
            doMobLoot
            false
                gamerule
                        doDaylightCycle
                    false
    execute as foo run
        gamemode
            survival

            @s[tag=bar]

            say hello
        execute in
            the_end
            run
            say foo
    gamerule doDaylightCycle
                         false

scoreboard players set #index global 3
scoreboard players set $index global 3
scoreboard players operation #sie_1_flags_delta integer = #sie_1_flags integer
execute store result score @s smithed.data run clear @s #smithed:crafter/all 0

# Multiline nbt paths

execute if data storage demo:foo a . b . c  run say hello

execute if data storage demo:foo
    thing1
        .thing2
        .thing3
    run
        say hello

execute if data storage demo:foo
    thing1
        .thing2{
            foo: 1,
            bar: [1, 2, 3],
        }
        .something_else
    run
        say hello

data modify entity @s Attributes[{
    Name: "minecraft:generic.movement_speed"
}].Modifiers append from storage demo:foo bar

data modify entity @s
    Attributes[{
        Name: "minecraft:generic.movement_speed"
    }]
    .Modifiers
    append from storage demo:foo bar

clear @s *[
    custom_data~{
        gm4_metallurgy: {
            stored_shamir: "lumos"
        }
    },
    damage | !max_item_stack=1,
]

execute if predicate {
  condition: weather_check,
  raining: true
}

particle minecraft:block{
  block_state: {
    Name: "minecraft:redstone_lamp",
    Properties: {
      lit: "true"
    }
  }
}
