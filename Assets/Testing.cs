using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class Testing : MonoBehaviour
{
    // Start is called before the first frame update
    void Start()
    {
        StartCoroutine(HttpApi.NewPlayer());
    }

    // Update is called once per frame
    void Update()
    {
        
    }
}
