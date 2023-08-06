using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class CourseLine : MonoBehaviour
{
    // Start is called before the first frame update
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        
    }

    public void Initialize(Vector3 startSquarePos, Vector3 endSquarePos)
    {
        // the course line should be in between the two squares and point from the start square to the end square
        Vector3 midPoint = (startSquarePos + endSquarePos) / 2;
        transform.position = midPoint;
        Vector3 direction = endSquarePos - startSquarePos;
        float angle = Mathf.Atan2(direction.y, direction.x) * Mathf.Rad2Deg;
        transform.rotation = Quaternion.Euler(0, 0, angle);
    }
}
